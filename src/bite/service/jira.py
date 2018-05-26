"""Support JIRA's REST interface.

API docs:
    - https://developer.atlassian.com/server/jira/platform/rest-apis/
    - https://docs.atlassian.com/jira/REST/server/
"""

from snakeoil.klass import aliased, alias

from ._jsonrest import JsonREST
from ._reqs import OffsetPagedRequest, req_cmd
from ._rest import RESTRequest, RESTParseRequest
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


class JiraPagedRequest(OffsetPagedRequest, RESTRequest):

    _offset_key = 'startAt'
    _size_key = 'maxResults'
    _total_key = 'total'


@req_cmd(Jira, cmd='search')
class _SearchRequest(RESTParseRequest, JiraPagedRequest):
    """Construct a search request."""

    def __init__(self, **kw):
        # use POST requests to avoid URL length issues with massive JQL queries
        super().__init__(endpoint='/search', method='POST', **kw)

    def parse(self, data):
        data = super().parse(data)
        issues = data['issues']
        for issue in issues:
            yield self.service.item(self.service, issue)

    @aliased
    class ParamParser(RESTParseRequest.ParamParser):

        # date field key map
        _date_fields = {
            'modified': 'updated',
            'viewed': 'lastViewed',
        }

        def __init__(self, **kw):
            super().__init__(**kw)
            self.query = []

        def _finalize(self, **kw):
            if not self.query:
                raise BiteError('no supported search terms or options specified')

            self.params['jql'] = ' AND '.join(self.query)

            # limit fields by default to decrease requested data size and speed up response
            fields = kw.get('fields')
            if fields is None:
                fields = ['id', 'assignee', 'summary']
            else:
                unknown_fields = set(fields).difference(self.service.item.attributes.keys())
                if unknown_fields:
                    raise BiteError(f"unknown fields: {', '.join(unknown_fields)}")
                self.options.append(f"Fields: {' '.join(fields)}")

            self.params['fields'] = fields

            # default to sorting ascending by ID
            sort = self.params.pop('sort', ['id'])

            # if configured for a specific project, limit search to specified project
            self.params['jql'] = (
                f"project = {self.service._project} "
                f"AND ( {self.params['jql']} ) "
                f"order by {', '.join(sort)}")

            self.request.fields = fields

        def id(self, k, v):
            id_strs = list(map(str, v))
            self.query.append(f"{k} in ({','.join(id_strs)})")
            self.options.append(f"IDs: {', '.join(id_strs)}")

        def attachments(self, k, v):
            val = 'not empty' if v else 'empty'
            display_val = 'yes' if v else 'no'
            self.query.append(f'{k} is {val}')
            self.options.append(f"{k.capitalize()}: {display_val}")

        def terms(self, k, v):
            for term in v:
                self.query.append(f'summary ~ "{term}"')
            self.options.append(f"Summary: {', '.join(map(str, v))}")

        @alias('modified', 'viewed', 'resolved')
        def created(self, k, v):
            field = self._date_fields.get(k, k)
            if v.start is not None:
                time_str = v.start.strftime('%Y-%m-%d %H:%M')
                self.query.append(f'{field} > "{time_str}"')
            if v.end is not None:
                time_str = v.end.strftime('%Y-%m-%d %H:%M')
                self.query.append(f'{field} < "{time_str}"')
            self.options.append(f'{k.capitalize()}: {v} ({v!r} UTC)')

        @alias('creator')
        def assigned_to(self, k, v):
            field = 'assignee' if k == 'assigned_to' else 'reporter'
            self.query.append(f"{field} in ({','.join(v)})")
            self.options.append(f"{field.capitalize()}: {', '.join(map(str, v))}")

        @alias('watchers')
        def votes(self, k, v):
            if v.start is not None:
                self.query.append(f'{k} >= {v.start}')
            if v.end is not None:
                self.query.append(f'{k} <= {v.end}')
            self.options.append(f"{k.capitalize()}: {v} ({v!r} {k})")
