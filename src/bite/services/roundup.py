"""XML-RPC access to Roundup

http://www.roundup-tracker.org/docs/xmlrpc.html
"""

import re

from datetime import datetime
import requests

from . import Request
from ._xmlrpc import Xmlrpc
from ..objects import decompress
from ..exceptions import AuthError, RequestError, ParsingError
from ..objects import Item, Attachment


class GetRequest(Request):

    def __init__(self, service, ids, fields=None, *args, **kw):
        """Construct a get request."""
        super().__init__(service)
        if not ids:
            raise ValueError('No {} ID(s) specified'.format(self.service.item_name))

        self.requests = []
        for i in ids:
            params = ['issue' + str(i)]
            if fields is not None:
                params.extend(fields)
            else:
                params.extend(self.service.item.attributes.keys())
            self.requests.append(self.service.create_request(method='display', params=params))

    def send(self):
        for data in self.service.parallel_send(self.requests):
            yield self.parse(data)

    def parse(self, data):
        return self.service.item(self.service, **data)


class Roundup(Xmlrpc):
    """Support Roundup's XML-RPC interface."""

    def __init__(self, **kw):
        # cached value mappings
        self.status = ()
        self.priority = ()
        self.users = ()

        kw['endpoint'] = '/xmlrpc'
        super().__init__(**kw)

        self.item = RoundupIssue
        self.item_type = 'issue'
        self.item_web_endpoint = '/issue'
        self.attachment = RoundupAttachment

    def inject_auth(self, request, params):
        request.headers['Authorization'] = self.auth_token
        return request, params

    def login(self, user=None, password=None):
        """Authenticate a session."""
        super().login(user, password)
        # XXX: Hacky method of saving the HTTP basic auth token, probably
        # should auth token usage to support setting session.auth or
        # session.headers as well so it doesn't have to be injected every time.
        request = requests.Request(method='POST')
        requests.auth.HTTPBasicAuth(user, password)(request)
        self.auth_token = request.headers['Authorization']

    def _cache_update(self):
        """Pull latest data from service for cache update."""
        config_updates = {}
        reqs = []

        # get possible status values
        reqs.append(self.create_request(method='list', params=['status']))

        # get possible priority values
        reqs.append(self.create_request(method='list', params=['priority']))

        # get possible user values requires login, otherwise returns empty list
        self.skip_auth = False
        self.load_auth_token()
        reqs.append(self.create_request(method='list', params=['user']))

        status, priority, users = self.parallel_send(reqs, size=3)

        # don't sort, ordering is important for the mapping to work properly
        config_updates['status'] = ', '.join(status)
        config_updates['priority'] = ', '.join(priority)
        if users:
            config_updates['users'] = ', '.join(users)

        return config_updates

    def _load_cache(self, settings):
        """Set attrs from cached data."""
        for k, v in settings:
            if k in ('status', 'priority', 'users'):
                setattr(self, k, tuple(x.strip() for x in v.split(',')))
            else:
                setattr(self, k, v)

    def create(self, title, **kw):
        """Create a new issue given a list of parameters

        :returns: ID of the newly created issue
        :rtype: int
        """
        params = ['issue']
        params.append('title={}'.format(title))
        for k, v in self.item.attributes.items():
            if kw.get(k, None) is not None:
                params.append("{}={}".format(k, kw[k]))

        req = self.create_request(method='create', params=params)
        data = self.send(req)
        return data

    def get(self, ids, fields=None, get_comments=False, get_attachments=False, **kw):
        return GetRequest(self, ids, fields)

    def modify(self, id, **kw):
        params = ['issue' + str(id[0])]
        for k, v in self.item.attributes.items():
            if kw.get(k, None) is not None:
                params.append("{}={}".format(k, kw[k]))

        req = self.create_request(method='set', params=params)
        data = self.send(req)
        return data

    def search(self, ids=None, **kw):
        params = ['issue', ids]
        search_params = {}
        if kw['terms']:
            search_params['title'] = kw['terms']
        for k, v in self.item.attributes.items():
            if kw.get(k, None) is not None:
                search_params[k] = kw[k]
        params.append(search_params)

        print(params)
        req = self.create_request(method='filter', params=params)
        data = self.send(req)
        print(data)
        return data

    def parse_response(self, response):
        """Send request object and perform checks on the response."""
        try:
            data = super().parse_response(response)
        except RequestError as e:
            # XXX: Hacky method of splitting off exception class from error string,
            # should probably move to using a regex or similar.
            msg = e.msg.split('>', 1)[1]
            raise RequestError(msg=msg, code=e.code, text=e.text)

        return data


class RoundupIssue(Item):
    attributes = {
        'assignedto': 'Assignee',
        'files': 'Attachments',
        'keyword': 'Keywords',
        'priority': 'Priority',
        'status': 'Status',
        'title': 'Title',
        'nosy': 'Nosy List',
    }

    def __init__(self, service, **kw):
        self.service = service
        for k, v in kw.items():
            setattr(self, k, v)

    def __str__(self):
        lines = []
        print_fields = [
            ('title', 'Title'),
            ('assignedto', 'Assignee'),
            ('status', 'Status'),
            ('keyword', 'Keywords'),
            ('files', 'Attachments'),
        ]

        for field, title in print_fields:
            value = getattr(self, field)
            if value is None:
                continue

            values = value
            if isinstance(value, list):
                values = ', '.join(map(str, value))

            lines.append('{:<12}: {}'.format(title, values))

        return '\n'.join(lines)


class RoundupAttachment(Attachment):
    def __init__(self, id, file_name, size=None, content_type=None,
                 data=None, creation_time=None, last_change_time=None, **kw):

        super().__init__(
            id=id, filename=file_name, size=size, mimetype=content_type,
            data=data, created=creation_time, modified=last_change_time)
