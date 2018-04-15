"""Gitlab service support.

API docs: https://docs.gitlab.com/ee/api/
"""

from dateutil.parser import parse as parsetime
from snakeoil.klass import aliased, alias
from urllib.parse import urlparse, urlunparse, quote_plus

from ._jsonrest import JsonREST
from ..exceptions import RequestError
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
            if k in ('created_at', 'updated_at', 'closed_at') and v:
                v = parsetime(v)
            if k in ('author', 'assignee') and v:
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
        self.webbase = base

        # extract gitlab domain
        url = urlparse(base)
        # TODO: generalize and allow versioned API support
        api_base = urlunparse((
            url.scheme,
            url.netloc,
            '/api/v4',
            None, None, None))

        self._api_base = api_base
        self._project = url.path.strip('/')

        # gitlab maxes out at 100 results per page
        if max_results is None:
            max_results = 100

        super().__init__(
            endpoint=f"/projects/{quote_plus(self._project)}", base=self._api_base,
            max_results=max_results, **kw)

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

        def _finalize(self, **kw):
            if not self.params:
                raise BiteError('no supported search terms or options specified')

            # default to returning only open issues
            self.params.setdefault('status', 'opened')

            # don't restrict scope by default
            self.params.setdefault('scope', 'all')

            # show issues in ascending order by default
            self.params.setdefault('sort', 'asc')

        def terms(self, k, v):
            self.params['search'] = v
            self.options.append(f"Summary: {', '.join(map(str, v))}")

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
