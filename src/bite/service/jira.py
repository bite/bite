"""Support JIRA's REST interface.

API docs:
    - https://developer.atlassian.com/server/jira/platform/rest-apis/
    - https://docs.atlassian.com/jira/REST/server/
"""

from ._jsonrest import JsonREST
from ._reqs import OffsetPagedRequest, ParseRequest, req_cmd
from ._rest import RESTRequest
from ..exceptions import BiteError, RequestError
from ..objects import Item


class JiraError(RequestError):
    """Jira service specific error."""

    def __init__(self, msg, code=None, text=None):
        msg = f'Jira error: {msg}'
        super().__init__(msg, code, text)


class JiraIssue(Item):

    attributes = {
    }

    attribute_aliases = {
        'title': 'summary',
        'owner': 'assignee',
    }

    type = 'issue'

    def __init__(self, service, issue):
        for k, v in issue.items():
            if k == 'id':
                setattr(self, k, v)
            elif k == 'fields':
                for kp, vp in v.items():
                    if kp == 'summary':
                        setattr(self, kp, vp)
                    elif kp == 'assignee':
                        if vp:
                            assignee = vp.get('name')
                        else:
                            assignee = 'unassigned'
                        setattr(self, kp, assignee)


class Jira(JsonREST):
    """Service supporting the Jira-based issue trackers."""

    _service = 'jira'

    item = JiraIssue
    item_endpoint = '/issues/{project}-{{id}}'

    def __init__(self, base, max_results=None, **kw):
        try:
            api_base, project = base.split('/projects/', 1)
            project = project.strip('/')
        except ValueError as e:
            raise BiteError(f'invalid project base: {base!r}')
        self._project = project
        self.item_endpoint = self.item_endpoint.format(project=project)
        # most jira instances default to 1k results per query
        if max_results is None:
            max_results = 1000
        # TODO: generalize and allow versioned API support
        super().__init__(
            endpoint=f"/rest/api/2", base=api_base, max_results=max_results, **kw)
        self.webbase = base

    def inject_auth(self, request, params):
        raise NotImplementedError

    def parse_response(self, response):
        data = super().parse_response(response)
        if 'errorMessages' not in data:
            return data
        else:
            self.handle_error(code=response.status_code, msg=data['errorMessages'][0])

    @staticmethod
    def handle_error(code, msg):
        """Handle Jira specific errors."""
        raise JiraError(msg=msg, code=code)


class JiraPagedRequest(RESTRequest, OffsetPagedRequest):

    _offset_key = 'startAt'
    _size_key = 'maxResults'
    _total_key = 'total'


@req_cmd(Jira, cmd='search')
class _SearchRequest(JiraPagedRequest, ParseRequest):
    """Construct a search request."""

    def __init__(self, *args, **kw):
        # use POST requests to avoid URL length issues with massive JQL queries
        super().__init__(*args, endpoint='/search', method='POST', **kw)

    def parse(self, data):
        super().parse(data)
        issues = data['issues']
        for issue in issues:
            yield self.service.item(self.service, issue)

    class ParamParser(ParseRequest.ParamParser):

        def __init__(self, request):
            super().__init__(request)
            self.query = []

        def _finalize(self, **kw):
            if not self.query:
                raise BiteError('no supported search terms or options specified')

            self.params['jql'] = ' AND '.join(self.query)

            # limit fields by default to decrease requested data size and speed up response
            fields = kw.get('fields', None)
            if fields is None:
                fields = ['id', 'assignee', 'summary']
            else:
                unknown_fields = set(fields).difference(self.service.item.attributes.keys())
                if unknown_fields:
                    raise BiteError(f"unknown fields: {', '.join(unknown_fields)}")
                self.options.append(f"Fields: {' '.join(fields)}")

            self.params['fields'] = fields
            # if configured for a specific project, limit search to specified project
            self.params['jql'] = f"project = {self.service._project} AND ( {self.params['jql']} )"

            self.request.fields = fields

        def terms(self, k, v):
            for term in v:
                self.query.append(f'summary ~ {term}')
            self.options.append(f"Summary: {', '.join(map(str, v))}")
