"""Support Bitbucket's REST interface.

API docs:
    https://api.bitbucket.org/
    https://developer.atlassian.com/cloud/bitbucket/

Updates:
    https://blog.bitbucket.org/
"""

from . import RESTRequest, LinkPagedRequest, req_cmd
from ..exceptions import BiteError, RequestError
from ._jsonrest import JsonREST
from ..objects import Item


class BitbucketError(RequestError):
    """Bitbucket service specific error."""

    def __init__(self, msg, code=None, text=None):
        msg = f'Bitbucket error: {msg}'
        super().__init__(msg, code, text)


class BitbucketIssue(Item):

    attributes = {
        'assignee': 'Assignee',
        'id': 'ID',
        'title': 'Title',
    }

    attribute_aliases = {
        'title': 'summary',
        'owner': 'assignee',
    }

    type = 'issue'

    def __init__(self, service, issue):
        for k in self.attributes.keys():
            v = issue.get(k, None)
            if k == 'assignee' and v:
                v = v['username']
            setattr(self, k, v)


class Bitbucket(JsonREST):
    """Service supporting the Bitbucket-based issue trackers."""

    _service = 'bitbucket'

    item = BitbucketIssue
    item_endpoint = '/issues/{id}'

    def __init__(self, base, max_results=None, **kw):
        try:
            api_base, user, repo = base.rstrip('/').rsplit('/', 2)
        except ValueError as e:
            raise BiteError(f'invalid project base: {base!r}')
        api_base = f'{api_base}/api/2.0'
        endpoint = f'/repositories/{user}/{repo}'
        # bitbucket cloud supports 100 results per page
        if max_results is None:
            max_results = 100
        # TODO: generalize and allow versioned API support
        super().__init__(
            endpoint=endpoint, base=api_base, max_results=max_results, **kw)
        self.webbase = base

    def inject_auth(self, request, params):
        raise NotImplementedError

    def parse_response(self, response):
        data = super().parse_response(response)
        if data.get('type', None) != 'error':
            return data
        else:
            self.handle_error(code=response.status_code, msg=data['error']['message'])

    @staticmethod
    def handle_error(code, msg):
        """Handle Bitbucket specific errors."""
        raise BitbucketError(msg=msg, code=code)


@req_cmd(Bitbucket, 'search')
class _SearchRequest(LinkPagedRequest, RESTRequest):
    """Construct a search request."""

    _page = 'page'
    _pagelen = 'pagelen'
    _next = 'next'
    _previous = 'previous'

    def __init__(self, service, **kw):
        params, options = self.parse_params(service=service, **kw)
        if not params:
            raise BiteError('no supported search terms or options specified')

        super().__init__(service=service, endpoint='/issues', params=params, **kw)
        self.options = options

    def parse_params(self, service, params=None, options=None, **kw):
        params = params if params is not None else {}
        options = options if options is not None else []
        query = []

        for k, v in ((k, v) for (k, v) in kw.items() if v):
            if k == 'terms':
                or_queries = []
                display_terms = []
                for term in v:
                    or_terms = term.split(',')
                    or_search_terms = [f'title ~ "{x}"' for x in or_terms]
                    or_display_terms = [f'"{x}"' for x in or_terms]
                    if len(or_terms) > 1:
                        or_queries.append(f"({' OR '.join(or_search_terms)})")
                        display_terms.append(f"({' OR '.join(or_display_terms)})")
                    else:
                        or_queries.append(or_search_terms[0])
                        display_terms.append(or_display_terms[0])
                query.append(f"{' AND '.join(or_queries)}")
                options.append(f"Summary: {' AND '.join(display_terms)}")

        params['q'] = ' AND '.join(query)
        return params, options

    def parse(self, data):
        if self._total is None:
            self._total = data['size']
        self._next_page = data.get(self._next, None)
        issues = data['values']
        for issue in issues:
            yield self.service.item(self.service, issue)
