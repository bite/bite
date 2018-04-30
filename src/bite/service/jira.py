"""Support JIRA's REST interface.

API docs:
    - https://developer.atlassian.com/server/jira/platform/rest-apis/
    - https://docs.atlassian.com/jira/REST/server/
"""

from ._jsonrest import JsonREST
from ._reqs import RESTRequest, OffsetPagedRequest, req_cmd
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


@req_cmd(Jira, 'search')
class _SearchRequest(RESTRequest, OffsetPagedRequest):
    """Construct a search request."""

    _offset_key = 'startAt'
    _size_key = 'maxResults'
    _total_key = 'total'

    def __init__(self, service, **kw):
        params, options = self.parse_params(service=service, **kw)
        if not params:
            raise BiteError('no supported search terms or options specified')

        # limit fields by default to decrease requested data size and speed up response
        fields = kw.get('fields', None)
        if fields is None:
            fields = ['id', 'assignee', 'summary']
        else:
            unknown_fields = set(fields).difference(service.item.attributes.keys())
            if unknown_fields:
                raise BiteError(f"unknown fields: {', '.join(unknown_fields)}")
            options.append(f"Fields: {' '.join(fields)}")

        params['fields'] = fields
        # if configured for a specific project, limit search to specified project
        params['jql'] = f"project = {service._project} AND ( {params['jql']} )"

        # use POST requests to avoid URL length issues with massive JQL queries
        super().__init__(service=service, endpoint='/search',
                         method='POST', params=params, **kw)
        self.fields = fields
        self.options = options

    def parse_params(self, service, params=None, options=None, **kw):
        params = params if params is not None else {}
        options = options if options is not None else []
        jql = []

        for k, v in ((k, v) for (k, v) in kw.items() if v):
            if k == 'terms':
                for term in v:
                    jql.append(f'summary ~ {term}')
            options.append(f"Summary: {', '.join(map(str, v))}")

        params['jql'] = ' AND '.join(jql)
        return params, options

    def parse(self, data):
        super().parse(data)
        issues = data['issues']
        for issue in issues:
            yield self.service.item(self.service, issue)
