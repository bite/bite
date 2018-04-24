"""Support Redmine's REST interface.

API docs:
    - http://www.redmine.org/projects/redmine/wiki/Rest_api
"""

from .. import RESTRequest, PagedRequest, req_cmd
from .._rest import REST
from ...exceptions import BiteError, RequestError
from ...objects import Item


class RedmineError(RequestError):
    """Redmine service specific error."""

    def __init__(self, msg, code=None, text=None):
        msg = f'Redmine error: {msg}'
        super().__init__(msg, code, text)


class RedmineIssue(Item):

    attributes = {
    }

    attribute_aliases = {
        'title': 'summary',
    }

    _print_fields = (
        ('title', 'Title'),
        ('id', 'ID'),
        ('created', 'Reported'),
    )

    type = 'issue'

    def __init__(self, service, issue):
        for k, v in issue.items():
            setattr(self, k, v)


class Redmine(REST):
    """Service supporting the Redmine-based issue trackers."""

    item = RedmineIssue
    item_endpoint = '/issues/{id}'

    def __init__(self, *args, max_results=None, **kw):
        # most redmine instances default to 100 results per query
        if max_results is None:
            max_results = 100
        super().__init__(*args, max_results=max_results, **kw)

    def inject_auth(self, request, params):
        raise NotImplementedError

    @staticmethod
    def handle_error(code, msg):
        """Handle Redmine specific errors."""
        raise RedmineError(msg=msg, code=code)


@req_cmd(Redmine, 'search')
class _SearchRequest(PagedRequest, RESTRequest):
    """Construct a search request.

    Assumes the elastic search plugin is installed:
        http://www.redmine.org/plugins/redmine_elasticsearch
        https://github.com/Restream/redmine_elasticsearch/wiki/Search-Quick-Reference
    """

    _offset_key = 'offset'
    _size_key = 'limit'

    def __init__(self, service, **kw):
        params, options = self.parse_params(service=service, **kw)
        if not params:
            raise BiteError('no supported search terms or options specified')

        super().__init__(service=service, endpoint=f'/search.{service._ext}', params=params, **kw)
        self.options = options

    def parse_params(self, service, params=None, options=None, **kw):
        params = params if params is not None else {}
        options = options if options is not None else []

        for k, v in ((k, v) for (k, v) in kw.items() if v):
            if k == 'terms':
                params['q'] = '+'.join(v)
                options.append(f"Summary: {', '.join(map(str, v))}")

        return params, options

    def parse(self, data):
        if self._total is None:
            self._total = data['total_count']
        issues = data['results']
        for issue in issues:
            yield self.service.item(self.service, issue)
