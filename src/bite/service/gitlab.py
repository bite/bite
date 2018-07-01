"""Gitlab service support.

API docs: https://docs.gitlab.com/ee/api/
"""

from dateutil.parser import parse as parsetime
from snakeoil.klass import aliased, alias
from urllib.parse import urlparse, urlunparse, quote_plus

from ._jsonrest import JsonREST
from ..exceptions import RequestError, BiteError
from ..objects import Item, Attachment, Comment, TimeInterval
from ._reqs import LinkHeaderPagedRequest, PagedRequest, ParseRequest, req_cmd
from ._rest import RESTRequest


class GitlabError(RequestError):

    def __init__(self, msg, code=None, text=None):
        msg = 'Gitlab error: ' + msg
        super().__init__(msg, code, text)


class GitlabIssue(Item):

    attributes = {
        'created': 'Created',
        'updated': 'Modified',
    }

    attribute_aliases = {
        'title': 'summary',
        'creator': 'author',
        'owner': 'assignee',
    }

    _print_fields = (
        ('summary', 'Title'),
        ('assignee', 'Assignee'),
        ('id', 'ID'),
    )

    type = 'issue'

    def __init__(self, comments=None, attachments=None, **kw):
        for k, v in kw.items():
            # TODO: fix this once support for global connections are enabled
            # skip global IDs and only use project IDs for now
            # https://docs.gitlab.com/ee/api/README.html#id-vs-iid
            if k == 'id':
                continue
            elif k == 'iid':
                k = 'id'
            elif k in ('created_at', 'updated_at', 'closed_at') and v:
                v = parsetime(v)
            elif k in ('author', 'assignee') and v:
                v = v['username']
            setattr(self, k, v)

        self.attachments = attachments if attachments is not None else ()
        self.comments = comments if comments is not None else ()


class GitlabComment(Comment):
    pass


class GitlabAttachment(Attachment):
    pass


class Gitlab(JsonREST):
    """Service supporting the Gitlab issue tracker."""

    _service = 'gitlab'
    _service_error_cls = GitlabError

    item = GitlabIssue
    item_endpoint = '/issues'
    attachment = GitlabAttachment
    #attachment_endpoint = '/file'

    def __init__(self, base, max_results=None, **kw):
        # extract gitlab domain
        url = urlparse(base)
        # TODO: generalize and allow versioned API support
        api_base = urlunparse((
            url.scheme,
            url.netloc,
            '/api/v4',
            None, None, None))

        paths = url.path.strip('/').split('/')
        try:
            org, project = paths
            self.repo = f'{org}/{project}'
        except ValueError:
            org = paths[0] if paths[0] else None
            self.repo = None
        self.org = org

        # gitlab maxes out at 100 results per page
        if max_results is None:
            max_results = 100

        # use endpoint for namespaced API calls:
        # https://docs.gitlab.com/ee/api/README.html#namespaced-path-encoding
        endpoint = f"/projects/{quote_plus(self.repo)}" if self.repo is not None else ''

        super().__init__(endpoint=endpoint, base=api_base, max_results=max_results, **kw)

        self.webbase = base

    def parse_response(self, response):
        data = super().parse_response(response)
        if 'error' not in data:
            return data
        else:
            self.handle_error(code=response.status_code, msg=data['error'])


class GitlabPagedRequest(PagedRequest, LinkHeaderPagedRequest, RESTRequest):
    """Requests supporting gitlab's pagination method.

    Docs: https://docs.gitlab.com/ee/api/README.html#pagination
    """

    # Gitlab supports link headers as the canonical method for pagination, but
    # it also provides parameters to request a given page so use those instead
    # in order to easily generate async calls for future pages. Note that the
    # total size of the query is still extracted from the headers though since
    # that information isn't provided in the data response.

    _page_key = 'page'
    _size_key = 'per_page'
    _total_key = 'NONE'
    _total_header = 'X-Total'

    # gitlab defaults to starting at page 1
    _start_page = 1


# TODO: Add more specific Elasticsearch functionality to another search req
# class, especially since gitlab.com doesn't support elasticsearch queries yet
# but newer self-hosted instances should.
@req_cmd(Gitlab, cmd='search')
class _SearchRequest(ParseRequest, GitlabPagedRequest):
    """Construct a search request.

    Gitlab uses Elasticsearch on the backend so advanced queries use its syntax.

    Docs: https://docs.gitlab.com/ee/user/search/advanced_search_syntax.html
    """

    # map from standardized kwargs name to expected service parameter name
    _params_map = {
        'status': 'state',
    }

    def __init__(self, **kw):
        super().__init__(endpoint='/issues', **kw)

    def parse(self, data):
        issues = super().parse(data)
        for issue in issues:
            yield self.service.item(**issue)

    @aliased
    class ParamParser(ParseRequest.ParamParser):

        # map of allowed status input values to service parameters, aliases are
        # capitalized
        _status_map = {
            'open': 'opened',
            'closed': 'closed',
            'ALL': 'ALL',
        }

        def _finalize(self, **kw):
            if not self.params:
                raise BiteError('no supported search terms or options specified')

            # default to returning only open issues
            self.params.setdefault('status', 'opened')
            # status must be unset to search across all values
            if self.params['status'] == 'ALL':
                del self.params['status']

            # don't restrict scope by default
            self.params.setdefault('scope', 'all')

            # show issues in ascending order by default
            self.params.setdefault('sort', 'asc')

        def terms(self, k, v):
            self.params['search'] = v
            self.options.append(f"Summary: {', '.join(v)}")

        def id(self, k, v):
            self.params['iids[]'] = v
            self.options.append(f"IDs: {', '.join(map(str, v))}")

        def labels(self, k, v):
            self.params[k] = ','.join(v)
            self.options.append(f"{k.capitalize()}: {', '.join(v)}")

        def milestone(self, k, v):
            self.params[k] = v
            self.options.append(f"{k.capitalize()}: {v}")

        def status(self, k, v):
            value = self._status_map.get(v)
            if value is None:
                raise BiteError(
                    f"invalid status value: {v} "
                    f"(available: {', '.join(sorted(self._status_map))})")
            self.params[k] = value
            self.options.append(f"{k.capitalize()}: {v}")

        @alias('modified')
        def created(self, k, v):
            field = 'updated' if k == 'modified' else k
            if not isinstance(v, TimeInterval):
                v = TimeInterval(v)
            start, end = v
            if start:
                self.params[f'{field}_after'] = start.isoformat()
            if end:
                self.params[f'{field}_before'] = end.isoformat()
            self.options.append(f'{k.capitalize()}: {v}')
