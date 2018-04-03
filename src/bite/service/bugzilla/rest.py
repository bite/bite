from collections import deque

import requests

from . import (
    Bugzilla, BugzillaBug, BugzillaError, BugzillaAttachment, BugzillaComment, BugzillaEvent,
    SearchRequest, HistoryRequest,
    ExtensionsRequest, VersionRequest, FieldsRequest, ProductsRequest, UsersRequest)
from .. import ContinuedRequest, RESTRequest, req_cmd
from .._json import Json
from ...exceptions import RequestError
from ...objects import Item


class BugzillaRest(Bugzilla, Json):
    """Support Bugzilla's REST interface.

    API docs: http://bugzilla.readthedocs.io/en/latest/api/index.html#apis
    """
    _service = 'bugzilla-rest'

    def __init__(self, **kw):
        super().__init__(endpoint='/rest', **kw)
        self.item = BugzillaBug

    def inject_auth(self, request, params):
        if len(self.auth) > 16:
            self.session.headers['X-Bugzilla-Api-Key'] = str(self.auth)
        else:
            self.session.headers['X-Bugzilla-Token'] = str(self.auth)
        self.authenticated = True
        return request, params

    def parse_response(self, response):
        data = super().parse_response(response)
        if 'error' not in data:
            return data
        else:
            self.handle_error(code=data['code'], msg=data['message'])

    def _failed_http_response(self, response):
        # catch invalid REST API resource requests
        if response.status_code in (404,):
            self.parse_response(response)
        super()._failed_http_response(response)


@req_cmd(BugzillaRest, 'search')
class _SearchRequest(SearchRequest, RESTRequest):
    def __init__(self, *args, **kw):
        """Construct a search request."""
        super().__init__(endpoint='/bug', *args, **kw)


@req_cmd(BugzillaRest, 'history')
class _HistoryRequest(HistoryRequest, RESTRequest):
    def __init__(self, *args, **kw):
        """Construct a search request."""
        super().__init__(endpoint='/bug/{}/history', *args, **kw)
        self.endpoint = self.endpoint.format(self.params['ids'][0])
        self.params['ids'] = self.params['ids'][1:]


@req_cmd(BugzillaRest, 'extensions')
class _ExtensionsRequest(ExtensionsRequest, RESTRequest):
    def __init__(self, service):
        """Construct an extensions request."""
        super().__init__(service=service, endpoint='/extensions')


@req_cmd(BugzillaRest, 'version')
class _VersionRequest(VersionRequest, RESTRequest):
    def __init__(self, service):
        """Construct a version request."""
        super().__init__(service=service, endpoint='/version')


@req_cmd(BugzillaRest, 'fields')
class _FieldsRequest(FieldsRequest, RESTRequest):
    def __init__(self, *args, **kw):
        super().__init__(endpoint='/field/bug', *args, **kw)
        if self.params:
            self._params = self.params
            params = deque((k, i) for k, v in self.params.items() for i in v)
            self.endpoint = '{}/{}'.format(self.endpoint, params.popleft()[1])
            self.params = params


@req_cmd(BugzillaRest, 'products')
class _ProductsRequest(ProductsRequest, RESTRequest):
    def __init__(self, *args, **kw):
        super().__init__(endpoint='/product', *args, **kw)
        self.params = [(k, i) for k, v in self.params.items() for i in v]


@req_cmd(BugzillaRest, 'users')
class _UsersRequest(UsersRequest, RESTRequest):
    def __init__(self, *args, **kw):
        super().__init__(endpoint='/user', *args, **kw)
        self.params = [(k, i) for k, v in self.params.items() for i in v]


class RestBug(BugzillaBug):

    def __init__(self, bug, comments=None, attachments=None, history=None, **kw):
        for k, v in bug.items():
            try:
                if not v or v == '---':
                    # skip empty lists and blank fields
                    continue
                elif k in ['assigned_to', 'creator', 'qa_contact']:
                    if 'real_name' in v:
                        setattr(self, k, '{} ({})'.format(v['real_name'], v['name']))
                    else:
                        if v['name']:
                            setattr(self, k, v['name'])
                elif k == 'cc':
                    self.cc = [cc['name'] for cc in bug['cc']]
                elif k == 'flags':
                    self.flags = [flag['name'] for flag in bug['flags']]
                else:
                    if isinstance(v, str) and re.match(r'^\d\d\d\d-\d\d-\d\dT\d\d:\d\d:\d\dZ$', v):
                        setattr(self, k, parsetime(v))
                    else:
                        setattr(self, k, v)
            except (KeyError, AttributeError):
                continue

        self.attachments = attachments
        self.comments = comments
        self.history = history

    def __str__(self):
        lines = []
        print_fields = (
            ('summary', 'Title'),
            ('alias', 'Alias'),
            ('assigned_to', 'Assignee'),
            ('creator', 'Reporter'),
            ('qa_contact', 'QA Contact'),
            ('creation_time', 'Reported'),
            ('last_change_time', 'Updated'),
            ('status', 'Status'),
            ('resolution', 'Resolution'),
            ('dupe_of', 'Duplicate'),
            ('whiteboard', 'Whiteboard'),
            ('severity', 'Severity'),
            ('priority', 'Priority'),
            ('classification', 'Class'),
            ('product', 'Product'),
            ('component', 'Component'),
            ('platform', 'Platform'),
            ('op_sys', 'OS'),
            ('keywords', 'Keywords'),
            ('target_milestone', 'Target'),
            ('version', 'Version'),
            ('url', 'URL'),
            ('ref', 'Reference'),
            ('see_also', 'See also'),
            ('cc', 'CC'),
            ('blocks', 'Blocks'),
            ('depends_on', 'Depends'),
            ('flags', 'Flags'),
            ('groups', 'Groups'),
            ('estimated_time', 'Estimated'),
            ('deadline', 'Deadline'),
            ('actual_time', 'Actual'),
            ('remaining_time', 'Remaining'),
            #('id', 'ID'),
            #('is_cc_accessible', 'Is CC Accessible'),
            #('is_confirmed', 'Confirmed'),
            #('is_creator_accessible', 'Is Creator Accessible'),
            #('history', 'History'),
            #('attachments', 'Attachments'),
            #('comments', 'Comments'),
        )

        for field, title in print_fields:
            try:
                value = getattr(self, field)
            except AttributeError:
                continue

            values = value
            if isinstance(value, list):
                values = ', '.join(map(str, value))
            else:
                values = value
            lines.append('{:<12}: {}'.format(title, values))

        custom_fields = ((k, v) for (k, v) in vars(self).items()
                         if re.match(r'^cf_\w+$', k))
        for k, v in custom_fields:
            title = string.capwords(k[3:], '_')
            title = title.replace('_', ' ')
            lines.append('{:<12}: {}'.format(title, v))

        return '\n'.join(lines)
