from ._xmlrpc import Xmlrpc
from ..objects import decompress
from ..exceptions import AuthError, RequestError, ParsingError
from ..objects import Item, Attachment

import requests


class Roundup(Xmlrpc):
    """Support Roundup's XML-RPC interface."""

    def __init__(self, **kw):
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
        auth = requests.auth.HTTPBasicAuth(user, password)
        request = requests.Request(method='POST')
        auth(request)
        self.auth_token = request.headers['Authorization']

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

    def get(self, id, fields=None, **kw):
        params = ['issue' + str(id[0])]
        if fields is not None:
            params.extend(fields)

        req = self.create_request(method='display', params=params)
        data = self.send(req)
        return (self.item(self, **data),)

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
