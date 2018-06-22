"""Github service support.

API docs: https://developer.github.com/v3/
"""

from dateutil.parser import parse as parsetime
from snakeoil.klass import aliased, alias
from urllib.parse import urlparse

from ._jsonrest import JsonREST
from ..exceptions import RequestError, BiteError
from ..objects import Item, Attachment, Comment, TimeInterval
from ._reqs import LinkHeaderPagedRequest, PagedRequest, QueryParseRequest, req_cmd
from ._rest import RESTRequest


class GithubError(RequestError):

    def __init__(self, msg, code=None, text=None):
        msg = 'Github error: ' + msg
        super().__init__(msg, code, text)


class GithubIssue(Item):

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
        # TODO: map out which attrs to save instead of saving all
        for k, v in kw.items():
            if k == 'id':
                continue
            elif k == 'number':
                k = 'id'
            elif k == 'user':
                v = v['login']
            elif k in ('created_at', 'updated_at', 'closed_at') and v:
                v = parsetime(v)
            elif k == 'assignee' and v:
                v = v['login']
            setattr(self, k, v)

        self.attachments = attachments if attachments is not None else ()
        self.comments = comments if comments is not None else ()


class GithubComment(Comment):
    pass


class GithubAttachment(Attachment):
    pass


class GithubRest(JsonREST):
    """Service supporting the Github issue tracker via its v3 REST API."""

    _service = 'github-rest'
    _service_error_cls = GithubError

    item = GithubIssue
    item_endpoint = '/issues/{id}'
    attachment = GithubAttachment

    # TODO: Allow overarching service objects as well, similar to jira support.
    def __init__(self, base, max_results=None, **kw):
        # extract github project info
        url = urlparse(base)
        self._project = url.path.strip('/')

        # github maxes out at 100 results per page
        if max_results is None:
            max_results = 100

        super().__init__(base='https://api.github.com', max_results=max_results, **kw)

        self.session.headers.update({'Accept': 'application/vnd.github.v3+json'})
        self.webbase = base


class GithubPagedRequest(PagedRequest, LinkHeaderPagedRequest, RESTRequest):
    """Requests supporting github's pagination method.

    Docs: https://developer.github.com/v3/#pagination
    """

    # Github supports link headers as the canonical method for pagination, but
    # it also provides parameters to request a given page so use those instead
    # in order to easily generate async calls for future pages. Note that the
    # total size of the query is still extracted from the headers though since
    # that information isn't provided in the data response.

    _page_key = 'page'
    _size_key = 'per_page'
    _total_key = 'total_count'

    # github defaults to starting at page 1
    _start_page = 1


@req_cmd(GithubRest, cmd='search')
class _SearchRequest(QueryParseRequest, GithubPagedRequest):
    """Construct a search request.

    Docs: https://developer.github.com/v3/search/#search-issues
        https://help.github.com/articles/searching-issues-and-pull-requests/
    """

    # map from standardized kwargs name to expected service parameter name
    _params_map = {
        'status': 'state',
    }

    def __init__(self, **kw):
        super().__init__(endpoint='/search/issues', **kw)

    def parse(self, data):
        data = super().parse(data)
        issues = data['items']
        for issue in issues:
            yield self.service.item(**issue)

    @aliased
    class ParamParser(QueryParseRequest.ParamParser):

        # map of allowed status input values to service parameters, aliases are
        # capitalized
        _status_map = {
            'open': 'open',
            'closed': 'closed',
            'all': 'all',
        }

        def _finalize(self, **kw):
            if not self.query:
                raise BiteError('no supported search terms or options specified')

            # return issues relating to the specified project
            self.query.setdefault('repo', self.service._project)

            # default to returning only open issues
            self.query.setdefault('state', 'open')

            terms = self.query.pop('terms', None)
            if terms is not None:
                # default to searching only the title
                self.query.setdefault('in', 'title')
                # search terms don't have type prefix in query string
                self.query[''] = terms

            # create query string
            self.params['q'] = ' '.join(f'{k}:{v}' if k else v for k, v in self.query.items())

            # show issues in ascending order by default
            self.params.setdefault('sort', 'created')
            self.params.setdefault('order', 'asc')

        def terms(self, k, v):
            # TODO: support AND/OR ops
            self.query[k] = ' '.join(v)
            self.options.append(f"Summary: {', '.join(v)}")

        def label(self, k, v):
            disabled, enabled = v
            for x in disabled:
                self.query.add('-label', x)
            for x in enabled:
                self.query.add('label', x)
            self.options.append(f"{k.capitalize()}: {', '.join(disabled + enabled)}")

        @alias('modified', 'closed')
        def created(self, k, v):
            field = 'updated' if k == 'modified' else k
            if not isinstance(v, TimeInterval):
                v = TimeInterval(v)
            start, end = v
            if start and end:
                self.query[field] = f'{start.isoformat()}..{end.isoformat()}'
            elif start:
                self.query[field] = f'>={start.isoformat()}'
            elif end:
                self.query[field] = f'<={start.isoformat()}'
            self.options.append(f'{k.capitalize()}: {v}')
