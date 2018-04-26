"""XML-RPC access to Roundup.

API docs: http://www.roundup-tracker.org/docs/xmlrpc.html
"""

from base64 import b64encode
from itertools import chain
import re

from datetime import datetime
from snakeoil.sequences import iflatten_instance

from ._reqs import NullRequest, Request, RPCRequest, req_cmd, generator
from ._xmlrpc import Xmlrpc
from ..cache import Cache, csv2tuple
from ..exceptions import AuthError, RequestError, ParsingError
from ..objects import decompress, Item, Attachment, Comment


def parsetime(time):
    return datetime.strptime(time, '<Date %Y-%m-%d.%X.%f>')


class RoundupError(RequestError):

    def __init__(self, msg, code=None, text=None):
        msg = 'Roundup error: ' + msg
        super().__init__(msg, code, text)


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

    attribute_aliases = {
        'comments': 'messages',
        'attachments': 'files',
    }

    _print_fields = (
        ('title', 'Title'),
        ('assignedto', 'Assignee'),
        ('creation', 'Created'),
        ('creator', 'Reporter'),
        ('activity', 'Modified'),
        ('actor', 'Modified by'),
        ('id', 'ID'),
        ('status', 'Status'),
        ('priority', 'Priority'),
        ('superseder', 'Duplicate'),
        ('keyword', 'Keywords'),
        ('messages', 'Comments'),
        ('files', 'Attachments'),
    )

    type = 'issue'

    def __init__(self, service, comments=None, attachments=None, **kw):
        self.service = service
        for k, v in kw.items():
            if k in ('creation', 'activity'):
                setattr(self, k, parsetime(v))
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

        self.attachments = attachments if attachments is not None else []
        self.comments = comments if comments is not None else []


class RoundupComment(Comment):
    pass


class RoundupAttachment(Attachment):
    pass


class RoundupCache(Cache):

    def __init__(self, *args, **kw):
        # default to empty values
        defaults = {
            'status': (),
            'priority': (),
            'keyword': (),
            'users': (),
        }

        converters = {
            'status': csv2tuple,
            'priority': csv2tuple,
            'keyword': csv2tuple,
            'users': csv2tuple,
        }

        super().__init__(defaults=defaults, converters=converters, *args, **kw)


class Roundup(Xmlrpc):
    """Service supporting the Roundup issue tracker."""

    #_service = 'roundup'
    _cache_cls = RoundupCache

    item = RoundupIssue
    item_endpoint = '/issue{id}'
    attachment = RoundupAttachment
    attachment_endpoint = '/file{id}'

    def __init__(self, **kw):
        super().__init__(endpoint='/xmlrpc', **kw)

    @property
    def cache_updates(self):
        """Pull latest data from service for cache update."""
        config_updates = {}
        reqs = []

        # get possible status values
        reqs.append(RPCRequest(command='list', params=['status'], service=self))

        # get possible priority values
        reqs.append(RPCRequest(command='list', params=['priority'], service=self))

        # get possible keyword values
        reqs.append(RPCRequest(command='list', params=['keyword'], service=self))

        # get possible user values requires login, otherwise returns empty list
        self.skip_auth = False
        self.auth.read()
        reqs.append(RPCRequest(command='list', params=['user'], service=self))

        status, priority, keyword, users = self.send(reqs)

        # don't sort, ordering is important for the mapping to work properly
        config_updates['status'] = tuple(status)
        config_updates['priority'] = tuple(priority)
        config_updates['keyword'] = tuple(keyword)
        if users:
            config_updates['users'] = tuple(users)

        return config_updates

    def inject_auth(self, request, params):
        self.session.headers['Authorization'] = str(self.auth)
        self.authenticated = True
        return request, params

    def _get_auth_token(self, user, password, **kw):
        """Get an authentication token from the service."""
        # generate HTTP basic auth token
        if isinstance(user, str):
            user = user.encode('latin1')
        if isinstance(password, str):
            password = password.encode('latin1')
        authstr = 'Basic ' + (b64encode(b':'.join((user, password))).strip()).decode()
        return authstr

    # def create(self, title, **kw):
    #     """Create a new issue given a list of parameters
    #
    #     :returns: ID of the newly created issue
    #     :rtype: int
    #     """
    #     params = ['issue']
    #     params.append('title={}'.format(title))
    #     for k, v in self.item.attributes.items():
    #         if kw.get(k, None) is not None:
    #             params.append("{}={}".format(k, kw[k]))
    #
    #     req = self.create_request(method='create', params=params)
    #     data = self.send(req)
    #     return data
    #
    # def modify(self, id, **kw):
    #     params = ['issue' + str(id[0])]
    #     for k, v in self.item.attributes.items():
    #         if kw.get(k, None) is not None:
    #             params.append("{}={}".format(k, kw[k]))
    #
    #     req = self.create_request(method='set', params=params)
    #     data = self.send(req)
    #     return data
    #
    # def search(self, ids=None, **kw):
    #     params = ['issue', ids]
    #     search_params = {}
    #     if kw['terms']:
    #         search_params['title'] = kw['terms']
    #     for k, v in self.item.attributes.items():
    #         if kw.get(k, None) is not None:
    #             search_params[k] = kw[k]
    #     params.append(search_params)
    #
    #     req = self.create_request(method='filter', params=params)
    #     data = self.send(req)
    #     return data

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


@req_cmd(Roundup, 'get')
class _GetRequest(Request):

    def __init__(self, ids, service, fields=None, get_comments=False,
                 get_attachments=False, **kw):
        """Construct a get request."""
        if not ids:
            raise ValueError(f'No {service.item.type} ID(s) specified')

        reqs = []
        for i in ids:
            issue_reqs = []
            params = ['issue' + str(i)]
            if fields is not None:
                params.extend(fields)
            else:
                params.extend(service.item.attributes.keys())
            reqs.append(RPCRequest(service=service, command='display', params=params))

        super().__init__(service=service, reqs=reqs)
        self.ids = ids
        self.get_comments = get_comments
        self.get_attachments = get_attachments

    def handle_exception(self, e):
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
        issues = list(iflatten_instance(data, dict))

        file_reqs = []
        msg_reqs = []
        for issue in issues:
            file_ids = issue.get('files', [])
            issue_files = []
            if file_ids and self.get_attachments:
                issue_files.append(self.service.AttachmentsRequest(attachment_ids=file_ids))
            else:
                issue_files.append(NullRequest())

            msg_ids = issue.get('messages', [])
            issue_msgs = []
            if msg_ids and self.get_comments:
                issue_msgs.append(self.service.CommentsRequest(comment_ids=msg_ids))
            else:
                issue_msgs.append(NullRequest())

            file_reqs.append(issue_files)
            msg_reqs.append(issue_msgs)

        attachments = self.service.send(file_reqs)
        comments = self.service.send(msg_reqs)

        return (self.service.item(service=self.service, comments=next(comments),
                                  attachments=next(attachments), id=self.ids[i], **issue)
                for i, issue in enumerate(issues))


@req_cmd(Roundup, 'attachments')
class _AttachmentsRequest(Request):
    def __init__(self, service, ids=None, attachment_ids=None, get_data=False, *args, **kw):
        """Construct an attachments request."""
        super().__init__(service)
        # TODO: add support for specifying issue IDs
        if attachment_ids is None:
            raise ValueError('No attachment ID(s) specified')

        reqs = []
        for i in attachment_ids:
            params = ['file' + str(i)]
            fields = ['name', 'type', 'creator', 'creation']
            if get_data:
                fields.append('content')
            params.extend(fields)
            reqs.append(RPCRequest(service=service, command='display', params=params))

        super().__init__(service=service, reqs=reqs)
        self.ids = ids
        self.attachment_ids = attachment_ids

    @generator
    def parse(self, data):
        if self.attachment_ids:
            ids = self.attachment_ids
        else:
            ids = self.ids

        return [RoundupAttachment(id=ids[i], filename=d['name'], data=d.get('content', None),
                                  creator=self.service.cache['users'][int(d['creator'])-1],
                                  created=parsetime(d['creation']), mimetype=d['type'])
                for i, d in enumerate(data)]


@req_cmd(Roundup, 'comments')
class _CommentsRequest(Request):
    def __init__(self, service, ids=None, comment_ids=None, created=None, fields=None, *args, **kw):
        """Construct a comments request."""
        super().__init__(service)
        # TODO: add support for specifying issue IDs
        if comment_ids is None:
            raise ValueError('No comment ID(s) specified')

        reqs = []
        for i in comment_ids:
            params = ['msg' + str(i)]
            if fields is not None:
                params.extend(fields)
            reqs.append(RPCRequest(service=service, command='display', params=params))

        super().__init__(service=service, reqs=reqs)
        self.ids = ids
        self.comment_ids = comment_ids

    @generator
    def parse(self, data):
        if self.comment_ids:
            ids = self.comment_ids
        else:
            ids = self.ids

        return [RoundupComment(id=ids[i], count=i, text=d['content'], created=parsetime(d['date']),
                               creator=self.service.cache['users'][int(d['author'])-1])
                for i, d in enumerate(data)]
