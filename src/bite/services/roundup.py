"""XML-RPC access to Roundup

http://www.roundup-tracker.org/docs/xmlrpc.html
"""

from itertools import chain
import re

from datetime import datetime
import requests

from . import NullRequest, Request, command
from ._xmlrpc import LxmlXmlrpc
from ..objects import decompress
from ..exceptions import AuthError, RequestError, ParsingError
from ..objects import Item, Attachment, Comment


class RoundupError(RequestError):

    def __init__(self, msg, code=None, text=None):
        msg = 'Roundup error: ' + msg
        super().__init__(msg, code, text)


class Roundup(LxmlXmlrpc):
    """Support Roundup's XML-RPC interface."""

    def __init__(self, **kw):
        # cached value mappings
        kw['cache'] = {
            'status': (),
            'priority': (),
            'keyword': (),
            'users': (),
        }

        kw['endpoint'] = '/xmlrpc'
        super().__init__(**kw)

        self.item = RoundupIssue
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

        # get possible keyword values
        reqs.append(self.create_request(method='list', params=['keyword']))

        # get possible user values requires login, otherwise returns empty list
        self.skip_auth = False
        self.load_auth_token()
        reqs.append(self.create_request(method='list', params=['user']))

        status, priority, keyword, users = self.parallel_send(reqs, size=3)

        # don't sort, ordering is important for the mapping to work properly
        config_updates['status'] = ', '.join(status)
        config_updates['priority'] = ', '.join(priority)
        config_updates['keyword'] = ', '.join(keyword)
        if users:
            config_updates['users'] = ', '.join(users)

        return config_updates

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

        req = self.create_request(method='filter', params=params)
        data = self.send(req)
        return data

    def parse_response(self, response):
        """Send request object and perform checks on the response."""
        try:
            data = super().parse_response(response)
        except RequestError as e:
            # XXX: Hacky method of splitting off exception class from error string,
            # should probably move to using a regex or similar.
            code, msg = re.match(r"^<type '(.+)'>:(.+)$", e.msg).groups()
            raise RequestError(msg=msg, code=code, text=e.text)

        return data

@command('get', Roundup)
class GetRequest(Request):

    def __init__(self, service, ids, fields=None, get_comments=False,
                get_attachments=False, **kw):
        """Construct a get request."""
        super().__init__(service)
        if not ids:
            raise ValueError('No {} ID(s) specified'.format(self.service.item_name))

        for i in ids:
            reqs = []
            params = ['issue' + str(i)]
            if fields is not None:
                params.extend(fields)
            else:
                params.extend(self.service.item.attributes.keys())
            reqs.append(self.service.create_request(method='display', params=params))
            #
            # for call in ('attachments', 'comments'):
            #     if locals()['get_' + call]:
            #         reqs.append(getattr(Service, call)(self.service, ids))
            #     else:
            #         reqs.append(NullRequest(self.service))
            #
            self.requests.append(reqs[0])


    def send(self):
        try:
            return self.parse(self.service.parallel_send(self.requests))
        except RequestError as e:
            if e.code == 'exceptions.IndexError':
                # issue doesn't exist
                raise RoundupError(msg=e.msg)
            elif e.code == 'exceptions.KeyError':
                # field doesn't exist
                raise RoundupError(msg="field doesn't exist: {}".format(e.msg))
            raise

    def parse(self, data):
        issues = []
        files = {}
        messages = {}
        reqs = []
        for i, issue in enumerate(data):
            # files[i] = issue.get('files', [])
            # messages[i] = issue.get('messages', [])
            issues.append(issue)

        # TODO: get file/message content
        for v in set(chain.from_iterable(files.values())):
            reqs.append(self.service.create_request(method='display', params=['file' + v]))
        for v in set(chain.from_iterable(messages.values())):
            reqs.append(self.service.create_request(method='display', params=['msg' + v]))

        return (self.service.item(self.service, **issue) for issue in issues)

@command('attachments', Roundup)
class AttachmentsRequest(Request):
    def __init__(self, service, ids, attachment_ids=None, fields=None, *args, **kw):
        """Construct a attachments request."""
        super().__init__(service)
        if not ids:
            raise ValueError('No {} ID(s) specified'.format(self.service.item_name))

        for i in ids:
            params = ['file' + str(i)]
            if fields is not None:
                params.extend(fields)
            else:
                params.extend(self.service.attachment.attributes.keys())
            self.requests.append(self.service.create_request(method='display', params=params))


@command('comments', Roundup)
class CommentsRequest(Request):
    def __init__(self, service, ids, comment_ids=None, created=None, fields=None, *args, **kw):
        """Construct a comments request."""
        super().__init__(service)
        if not ids:
            raise ValueError('No {} ID(s) specified'.format(self.service.item_name))

        for i in ids:
            params = ['msg' + str(i)]
            if fields is not None:
                params.extend(fields)
            else:
                params.extend(self.service.item.attributes.keys())
            self.requests.append(self.service.create_request(method='display', params=params))


class RoundupIssue(Item):

    attributes = {
        'creator': 'Reporter',
        'creation': 'Created',
        'assignedto': 'Assignee',
        'keyword': 'Keywords',
        'priority': 'Priority',
        'status': 'Status',
        'title': 'Title',
        'nosy': 'Nosy List',
        'superseder': 'Duplicate of',
        'actor': 'Modified by',
        'activity': 'Modified',
        'messages': 'Comments',
        'files': 'Attachments',
    }

    endpoint = '/issue'
    type = 'issue'

    def __init__(self, service, **kw):
        self.service = service
        for k, v in kw.items():
            if k in ('creation', 'activity'):
                setattr(self, k, datetime.strptime(v, '<Date %Y-%m-%d.%X.%f>'))
            elif k in ('creator', 'actor'):
                try:
                    username = self.service.cache['users'][int(v)-1]
                except IndexError:
                    # cache needs update
                    username = v
                setattr(self, k, username)
            elif k == 'status':
                try:
                    status = self.service.cache['status'][int(v)-1]
                except IndexError:
                    # cache needs update
                    status = v
                setattr(self, k, status)
            elif k == 'priority' and v is not None:
                try:
                    priority = self.service.cache['priority'][int(v)-1]
                except IndexError:
                    # cache needs update
                    priority = v
                setattr(self, k, priority)
            elif k == 'keyword' and v is not None:
                keywords = []
                for keyword in v:
                    try:
                        keywords.append(self.service.cache['keyword'][int(keyword)-1])
                    except IndexError:
                        # cache needs update
                        keywords.append(keyword)
                setattr(self, k, keywords)
            else:
                setattr(self, k, v)

    def __str__(self):
        lines = []
        print_fields = [
            ('title', 'Title'),
            ('assignedto', 'Assignee'),
            ('creation', 'Created'),
            ('creator', 'Reporter'),
            ('activity', 'Modified'),
            ('actor', 'Modified by'),
            ('status', 'Status'),
            ('priority', 'Priority'),
            ('superseder', 'Duplicate'),
            ('keyword', 'Keywords'),
            ('messages', 'Comments'),
            ('files', 'Attachments'),
        ]

        for field, title in print_fields:
            value = getattr(self, field)
            if value is None:
                continue

            if field in ('messages', 'files'):
                value = len(value)

            if isinstance(value, list):
                value = ', '.join(map(str, value))

            lines.append('{:<12}: {}'.format(title, value))

        return '\n'.join(lines)


class RoundupComment(Comment):
    def __init__(self, comment, id, count, rest=False, **kw):
        self.comment_id = comment['id']

        super().__init__(
            id=id, creator=creator, date=date,
            count=count, changes=changes, text=text)


class RoundupAttachment(Attachment):

    endpoint = '/file'

    def __init__(self, id, file_name, size=None, content_type=None,
                 data=None, creation_time=None, last_change_time=None, **kw):

        super().__init__(
            id=id, filename=file_name, size=size, mimetype=content_type,
            data=data, created=creation_time, modified=last_change_time)
