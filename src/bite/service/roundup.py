"""XML-RPC access to Roundup.

API docs:
    http://www.roundup-tracker.org/docs/xmlrpc.html
    http://roundup.sourceforge.net/docs/user_guide.html#query-tracker
"""

from base64 import b64encode
from itertools import chain, repeat
import re

from datetime import datetime
from snakeoil.klass import aliased, alias

from ._reqs import NullRequest, Request, RPCRequest, ParseRequest, req_cmd, generator
from ._xmlrpc import Xmlrpc, XmlrpcError, Multicall
from ..cache import Cache, csv2tuple
from ..exceptions import RequestError, BiteError
from ..objects import decompress, Item, Attachment, Comment
from ..utc import utc


def parsetime(time):
    """Parse custom date format that roundup uses."""
    date = datetime.strptime(time, '<Date %Y-%m-%d.%X.%f>')
    # strip microseconds and assume UTC
    return date.replace(microsecond=0).astimezone(utc)


class RoundupError(RequestError):

    def __init__(self, msg, code=None, text=None):
        msg = 'Roundup error: ' + msg
        super().__init__(msg, code, text)


class RoundupIssue(Item):

    # assumes bugs.python.org issue schema
    attributes = {
        # from schema list
        'assignee': 'Assignee',
        'components': 'Components',
        'dependencies': 'Depends',
        'files': 'Attachments',
        'keywords': 'Keywords',
        # 'message_count': 'Comment count',
        'messages': 'Comments',
        'nosy': 'Nosy List',
        # 'nosy_count': 'Nosy count',
        'priority': 'Priority',
        'pull_requests': 'PRs',
        'resolution': 'Resolution',
        'severity': 'Severity',
        'stage': 'Stage',
        'status': 'Status',
        'superseder': 'Duplicate of',
        'title': 'Title',
        'type': 'Type',
        'versions': 'Versions',

        # properties not listed by schema output, but included by default
        'id': 'ID',
        'creator': 'Reporter',
        'creation': 'Created',
        'actor': 'Modified by',
        'activity': 'Modified',
    }

    attribute_aliases = {
        'owner': 'assignee',
        'created': 'creation',
        'modified': 'activity',
    }

    _print_fields = (
        ('title', 'Title'),
        ('assignee', 'Assignee'),
        ('creation', 'Created'),
        ('creator', 'Reporter'),
        ('activity', 'Modified'),
        ('actor', 'Modified by'),
        ('id', 'ID'),
        ('status', 'Status'),
        ('dependencies', 'Depends'),
        ('resolution', 'Resolution'),
        ('priority', 'Priority'),
        ('superseder', 'Duplicate'),
        ('keywords', 'Keywords'),
    )

    type = 'issue'

    def __init__(self, service, **kw):
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

    _service = 'roundup'
    _cache_cls = RoundupCache

    item = RoundupIssue
    item_endpoint = '/issue{id}'
    attachment = RoundupAttachment
    attachment_endpoint = '/file{id}'

    def __init__(self, **kw):
        super().__init__(endpoint='/xmlrpc', **kw)
        # bugs.python.org requires this header
        self.session.headers.update({
            'X-Requested-With': 'XMLHttpRequest'
        })

    @property
    def cache_updates(self):
        """Pull latest data from service for cache update."""
        config_updates = {}
        values = {}

        # login required to grab user data
        self.client.login(force=True)

        attrs = ('status', 'priority', 'keyword', 'user')
        reqs = []
        # pull list of specified attribute types
        names = list(self.multicall(method='list', params=attrs).send())

        # The list command doesn't return the related values in the order that
        # values their underlying IDs so we have to roll lookups across the
        # entire scope to determine them.
        for i, attr in enumerate(attrs):
            data = names[i]
            values[attr] = data
            params = ([attr, x] for x in data)
            reqs.append(self.multicall(method='lookup', params=params))

        data = self.merged_multicall(reqs=reqs).send()
        for attr in ('status', 'priority', 'keyword', 'user'):
            order = next(data)
            values[attr] = [x for order, x in sorted(zip(order, values[attr]))]

        # don't sort, ordering is important for the mapping to work properly
        config_updates['status'] = tuple(values['status'])
        config_updates['priority'] = tuple(values['priority'])
        config_updates['keyword'] = tuple(values['keyword'])
        if 'user' in values:
            config_updates['users'] = tuple(values['user'])

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

    def parse_response(self, response):
        """Send request object and perform checks on the response."""
        try:
            data = super().parse_response(response)
        except XmlrpcError as e:
            roundup_exc = re.match(r"^<\w+ '(.+)'>:(.+)$", e.msg)
            if roundup_exc:
                code, msg = roundup_exc.groups()
                raise RoundupError(msg=msg.lower(), code=code)
            raise

        return data


@req_cmd(Roundup, cmd='search')
class _SearchRequest(RPCRequest, ParseRequest):
    """Construct a search request."""

    # map from standardized kwargs name to expected service parameter name
    _params_map = {
        'created': 'creation',
        'modified': 'activity',
    }

    def __init__(self, *args, fields=None, **kw):
        super().__init__(*args, method='filter', **kw)

        # limit fields by default to decrease requested data size and speed up response
        if fields is None:
            fields = ['id', 'assignee', 'title']
        else:
            unknown_fields = set(fields).difference(self.service.item.attributes.keys())
            if unknown_fields:
                raise BiteError(f"unknown fields: {', '.join(unknown_fields)}")
            self.options.append(f"Fields: {' '.join(fields)}")
        self.fields = fields

    def parse(self, data):
        # Roundup search requests return a list of matching IDs that we resubmit
        # via a multicall to grab ticket data if any matches exist.
        if data:
            issues = self.service.GetItemRequest(ids=data, fields=self.fields).send()
            yield from issues

    @aliased
    class ParamParser(ParseRequest.ParamParser):

        # map of allowed sorting input values to service parameters
        _sorting_map = {
            'assignee': 'assignee',
            'id': 'id',
            'creator': 'creator',
            'created': 'creation',
            'modified': 'activity',
            'modified-by': 'actor',
            'components': 'components',
            'depends': 'dependencies',
            'keywords': 'keywords',
            'comments': 'message_count',
            'cc': 'nosy_count',
            'priority': 'priority',
            'prs': 'pull_requests',
            'resolution': 'resolution',
            'severity': 'severity',
            'stage': 'stage',
            'status': 'status',
            'title': 'title',
            'type': 'type',
        }

        def __init__(self, *args, **kw):
            super().__init__(*args, **kw)
            self._sort = None

        def _finalize(self, **kw):
            if not self.params:
                raise BiteError('no supported search terms or options specified')

            # default to sorting ascending by ID
            sort = self._sort if self._sort is not None else [('+', 'id')]

            # default to showing issues that aren't closed
            # TODO: use service cache with status names here
            if 'status' not in self.params:
                cached_statuses = self.service.cache['status']
                if cached_statuses:
                    open_statuses = list(
                        i + 1 for i, x in enumerate(cached_statuses) if x != 'closed')
                    self.params['status'] = open_statuses

            return 'issue', None, self.params, sort

        def terms(self, k, v):
            self.params['title'] = v
            self.options.append(f"Summary: {', '.join(v)}")

        @alias('modified')
        def created(self, k, v):
            self.params[k] = f"{v.strftime('%Y-%m-%d.%H:%M:%S')};."
            self.options.append(f'{k.capitalize()}: {v} (since {v.isoformat()})')

        def sort(self, k, v):
            sorting_terms = []
            for sort in v:
                if sort[0] == '-':
                    key = sort[1:]
                    order = '-'
                else:
                    key = sort
                    order = '+'
                try:
                    order_var = self._sorting_map[key]
                except KeyError:
                    choices = ', '.join(sorted(self._sorting_map.keys()))
                    raise BiteError(
                        f'unable to sort by: {key!r} (available choices: {choices}')
                sorting_terms.append((order, order_var))
            self._sort = sorting_terms
            self.options.append(f"Sort order: {', '.join(v)}")


@req_cmd(Roundup)
class _GetItemRequest(Multicall):
    """Construct an item request."""

    def __init__(self, ids, service, fields=None, **kw):
        if ids is None:
            raise ValueError(f'No {service.item.type} ID(s) specified')

        # Request all fields by default, roundup says it does this already when
        # no fields are specified, but it still doesn't return all fields.
        if fields is None:
            fields = service.item.attributes.keys()
        params = (chain([f'issue{i}'], fields) for i in ids)

        super().__init__(service=service, method='display', params=params, **kw)
        self.ids = ids

    def parse(self, data):
        # unwrap multicall result
        issues = super().parse(data)
        return (self.service.item(self.service, **issue)
                for i, issue in enumerate(issues))


@req_cmd(Roundup, cmd='get')
class _GetRequest(_GetItemRequest):
    """Construct a get request."""

    def __init__(self, *args, get_comments=False, get_attachments=False, **kw):
        super().__init__(*args, **kw)
        self._get_comments = get_comments
        self._get_attachments = get_attachments

    def handle_exception(self, e):
        if e.code == 'exceptions.IndexError':
            # issue doesn't exist
            raise RoundupError(msg=e.msg)
        elif e.code == 'exceptions.KeyError':
            # field doesn't exist
            raise RoundupError(msg="field doesn't exist: {}".format(e.msg))
        raise

    def parse(self, data):
        issues = list(super().parse(data))
        file_reqs = []
        msg_reqs = []

        for issue in issues:
            file_ids = issue.files
            issue_files = []
            if file_ids and self._get_attachments:
                issue_files.append(self.service.AttachmentsRequest(attachment_ids=file_ids))
            else:
                issue_files.append(NullRequest())

            msg_ids = issue.messages
            issue_msgs = []
            if msg_ids and self._get_comments:
                issue_msgs.append(self.service.CommentsRequest(comment_ids=msg_ids))
            else:
                issue_msgs.append(NullRequest())

            file_reqs.append(issue_files)
            msg_reqs.append(issue_msgs)

        attachments = self.service.send(file_reqs)
        comments = self.service.send(msg_reqs)
        # TODO: There doesn't appear to be a way to request issue changes via the API.
        # changes = self.service.ChangesRequest(ids=self.ids).send()

        for issue in issues:
            issue.attachments = next(attachments)
            issue.comments = next(comments)
            issue.changes = ()
            yield issue


@req_cmd(Roundup, cmd='attachments')
class _AttachmentsRequest(Multicall):
    def __init__(self, service, ids=None, attachment_ids=None, get_data=False, **kw):
        """Construct an attachments request."""
        # TODO: add support for specifying issue IDs
        if attachment_ids is None:
            raise ValueError('No attachment ID(s) specified')

        fields = ['name', 'type', 'creator', 'creation']
        if get_data:
            fields.append('content')
        params = (chain([f'file{i}'], fields) for i in attachment_ids)
        super().__init__(service=service, method='display', params=params, **kw)

        self.ids = ids
        self.attachment_ids = attachment_ids

    def parse(self, data):
        # unwrap multicall result
        data = super().parse(data)

        if self.attachment_ids:
            ids = self.attachment_ids
        else:
            ids = self.ids

        return [RoundupAttachment(id=ids[i], filename=d['name'], data=d.get('content', None),
                                  creator=d['creator'], created=parsetime(d['creation']), mimetype=d['type'])
                for i, d in enumerate(data)]


@req_cmd(Roundup, cmd='comments')
class _CommentsRequest(Multicall):
    def __init__(self, service, ids=None, comment_ids=None, created=None, fields=(), **kw):
        """Construct a comments request."""
        # TODO: add support for specifying issue IDs
        if comment_ids is None:
            raise ValueError('No comment ID(s) specified')

        params = (chain([f'msg{i}'], fields) for i in comment_ids)
        super().__init__(service=service, method='display', params=params, **kw)

        self.ids = ids
        self.comment_ids = comment_ids

    def parse(self, data):
        # unwrap multicall result
        data = super().parse(data)

        if self.comment_ids:
            ids = self.comment_ids
        else:
            ids = self.ids

        return [RoundupComment(id=ids[i], count=i, text=d['content'].strip(),
                               created=parsetime(d['date']), creator=d['author'])
                for i, d in enumerate(data)]


@req_cmd(Roundup, cmd='schema')
class _SchemaRequest(RPCRequest):
    """Construct a schema request."""

    def __init__(self, *args, **kw):
        super().__init__(*args, method='schema', **kw)
