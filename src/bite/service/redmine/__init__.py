"""Support Redmine's REST interface.

API docs:
    - http://www.redmine.org/projects/redmine/wiki/Rest_api
"""

from .._reqs import OffsetPagedRequest, ParseRequest, req_cmd
from .._rest import REST, RESTRequest
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

    def __init__(self, max_results=None, **kw):
        # most redmine instances default to 100 results per query
        if max_results is None:
            max_results = 100
        super().__init__(max_results=max_results, **kw)

    def inject_auth(self, request, params):
        raise NotImplementedError

    @staticmethod
    def handle_error(code, msg):
        """Handle Redmine specific errors."""
        raise RedmineError(msg=msg, code=code)


class RedminePagedRequest(OffsetPagedRequest, RESTRequest):

    _offset_key = 'offset'
    _size_key = 'limit'
    _total_key = 'total_count'


@req_cmd(Redmine, cmd='search')
class _SearchRequest(ParseRequest, RedminePagedRequest):
    """Construct a search request.

    Assumes the elastic search plugin is installed:
        http://www.redmine.org/plugins/redmine_elasticsearch
        https://github.com/Restream/redmine_elasticsearch/wiki/Search-Quick-Reference
    """

    def __init__(self, *, service, **kw):
        super().__init__(service=service, endpoint=f'/search.{service._ext}', **kw)

    def parse(self, data):
        data = super().parse(data)
        issues = data['results']
        for issue in issues:
            yield self.service.item(self.service, issue)

    class ParamParser(ParseRequest.ParamParser):

        def _finalize(self, **kw):
            if not self.params:
                raise BiteError('no supported search terms or options specified')

        def terms(self, k, v):
            self.params['q'] = '+'.join(v)
            self.options.append(f"Summary: {', '.join(map(str, v))}")
