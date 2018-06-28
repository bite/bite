"""Github service support.

API docs: https://developer.github.com/v3/
"""

from dateutil.parser import parse as parsetime
from snakeoil.klass import aliased, alias
from urllib.parse import urlparse, urlunparse

from ._jsonrest import JsonREST
from ..exceptions import RequestError, BiteError
from ..objects import Item, Attachment, Comment, TimeInterval, IntRange
from ._reqs import LinkHeaderPagedRequest, PagedRequest, QueryParseRequest, req_cmd
from ._rest import RESTRequest
from ..utils import dict2tuples


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
        api_base = urlunparse((
            url.scheme,
            f'api.{url.netloc}',
            '',
            None, None, None))

        paths = url.path.strip('/').split('/')
        try:
            org, project = paths
            self.repo = f'{org}/{project}'
        except ValueError:
            org = paths[0] if paths[0] else None
            self.repo = None
        self.org = org

        # github maxes out at 100 results per page
        if max_results is None:
            max_results = 100

        super().__init__(base=api_base, max_results=max_results, **kw)

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

    def __init__(self, **kw):
        super().__init__(endpoint='/search/issues', **kw)

    def parse(self, data):
        data = super().parse(data)
        issues = data['items']
        for issue in issues:
            yield self.service.item(**issue)

    @aliased
    class ParamParser(QueryParseRequest.ParamParser):

        # map of allowed state input values to service parameters, aliases are
        # capitalized
        _state_map = {
            'open': 'open',
            'closed': 'closed',
            'ALL': ('open', 'closed'),
        }

        def _finalize(self, **kw):
            if not self.query:
                raise BiteError('no supported search terms or options specified')

            if self.service.repo is not None:
                # return issues relating to the specified project
                self.query.setdefault('repo', self.service.repo)
            elif self.service.org is not None:
                # return issues relating to the specified organization
                self.query.setdefault('org', self.service.org)

            # default to returning only open issues
            self.query.setdefault('is', 'open')

            terms = self.query.pop('terms', None)
            if terms is not None:
                # default to searching only the title
                self.query.setdefault('in', 'title')
                # search terms don't have type prefix in query string
                self.query.add('', terms)

            # create query string
            self.params['q'] = ' '.join(
                f'{k}:{v}' if k else v for k, v in dict2tuples(self.query))

            # show issues in ascending order by default
            self.params.setdefault('sort', 'created')
            self.params.setdefault('order', 'asc')

        def terms(self, k, v):
            or_queries = []
            display_terms = []
            for term in v:
                or_terms = [x.replace('"', '\\"') for x in term.split(',')]
                or_display_terms = [f'"{x}"' for x in or_terms]
                if len(or_terms) > 1:
                    or_queries.append(f"({' OR '.join(or_terms)})")
                    display_terms.append(f"({' OR '.join(or_display_terms)})")
                else:
                    or_queries.append(or_terms[0])
                    display_terms.append(or_display_terms[0])
            self.query[k] = f"{' AND '.join(or_queries)}"
            self.options.append(f"Summary: {' AND '.join(display_terms)}")

        def label(self, k, v):
            disabled, enabled = v
            for x in disabled:
                self.query.add('-label', f'"{x}"')
            for x in enabled:
                if x == 'NONE':
                    self.query.add('', 'no:label')
                else:
                    self.query.add('label', f'"{x}"')
            disabled = [f'-{x}' for x in disabled]
            self.options.append(f"{k.capitalize()}: {', '.join(disabled + enabled)}")

        def state(self, k, v):
            for x in v:
                value = self._state_map.get(x)
                if value is None:
                    raise BiteError(
                        f"invalid state value: {x} "
                        f"(available: {', '.join(sorted(self._state_map))})")
                self.query.add('is', value)
            self.options.append(f"{k.capitalize()}: {', '.join(v)}")

        def milestone(self, k, v):
            disabled, enabled = v
            for x in disabled:
                self.query.add('-milestone', f'"{x}"')
            for x in enabled:
                if x == 'NONE':
                    self.query.add('', 'no:milestone')
                else:
                    self.query.add('milestone', f'"{x}"')
            disabled = [f'-{x}' for x in disabled]
            self.options.append(f"{k.capitalize()}: {', '.join(disabled + enabled)}")

        def comments(self, k, v):
            if isinstance(v, (str, tuple)):
                v = IntRange(v)
            start, end = v
            if start and end:
                self.query[k] = f'{start}..{end}'
            elif start:
                self.query[k] = f'>={start}'
            elif end:
                self.query[k] = f'<={end}'
            self.options.append(f"{k.capitalize()}: {v}")

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

        @alias('assignee', 'mentions', 'commenter')
        def creator(self, k, v):
            field = 'author' if k == 'creator' else k
            disabled, enabled = v
            for x in disabled:
                self.query.add(f'-{field}', x)
            for x in enabled:
                if k == 'assignee' and x == 'NONE':
                    self.query.add('', 'no:assignee')
                else:
                    self.query.add(field, x)
            disabled = [f'-{x}' for x in disabled]
            self.options.append(f"{k.capitalize()}: {', '.join(disabled + enabled)}")

        @alias('org')
        def user(self, k, v):
            self.query[k] = v
            self.options.append(f"{k.capitalize()}: {v}")

        def repo(self, k, v):
            if self.service.org is None and '/' not in v:
                raise BiteError(f'repo missing organization: {v!r}')
            self.query[k] = v
            self.options.append(f"{k.capitalize()}: {v}")


@req_cmd(GithubRest, cmd='pr_search')
class _PRSearchRequest(_SearchRequest):
    """Construct a search request for pull requests."""

    @aliased
    class ParamParser(_SearchRequest.ParamParser):

        # map of allowed state input values to service parameters, aliases are
        # capitalized
        _state_map = {
            'open': 'open',
            'closed': 'closed',
            'merged': 'merged',
            'unmerged': 'unmerged',
            'ALL': ('merged', 'unmerged'),
        }

        # map of allowed status input values to service parameters, aliases are
        # capitalized
        _status_map = {
            'pending': 'pending',
            'success': 'success',
            'failure': 'failure',
            'ALL': ('pending', 'success', 'failure'),
        }

        def _finalize(self, **kw):
            # limit search to pull requests
            self.query.setdefault('type', 'pr')

            super()._finalize(**kw)

        def merged(self, k, v):
            self.created(k, v)

        @alias('head', 'base')
        def _branch(self, k, v):
            self.query[k] = v
            self.options.append(f"{k.capitalize()}: {v}")

        def sha(self, k, v):
            self.query.add('', v)
            self.options.append(f"{k.upper()}: {v}")

        def status(self, k, v):
            for x in v:
                value = self._status_map.get(x)
                if value is None:
                    raise BiteError(
                        f"invalid status value: {x} "
                        f"(available: {', '.join(sorted(self._status_map))})")
                self.query.add('status', value)
            self.options.append(f"{k.capitalize()}: {', '.join(v)}")
