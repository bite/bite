"""Support Trac's RPC interface.

API docs:
    - https://trac-hacks.org/wiki/XmlRpcPlugin
    - https://trac.videolan.org/vlc/rpc
"""

from itertools import chain

from snakeoil.klass import aliased, alias

from .. import Service
from .._reqs import Request, ParseRequest, NullRequest, req_cmd, generator
from .._rpc import Multicall, MergedMulticall, RPCRequest
from ...exceptions import BiteError, RequestError
from ...objects import Item, Comment, Attachment, Change
from ...utils import dict2tuples


class TracError(RequestError):
    """Trac service specific error."""

    def __init__(self, msg, code=None, text=None):
        msg = f'Trac error: {msg}'
        super().__init__(msg, code, text)


class TracComment(Comment):
    pass


class TracAttachment(Attachment):
    pass


class TracEvent(Change):
    pass


class TracTicket(Item):

    attributes = {
        'cc': 'cc',
        'created': 'Created',
        'modified': 'Modified',
        'owner': 'Assignee',
        'reporter': 'Reporter',
    }

    attribute_aliases = {
        'title': 'summary',
    }

    _print_fields = (
        ('title', 'Title'),
        ('id', 'ID'),
        ('created', 'Reported'),
        ('modified', 'Updated'),
        ('status', 'Status'),
        ('resolution', 'Resolution'),
        ('reporter', 'Reporter'),
        ('owner', 'Assignee'),
        ('cc', 'CC'),
        ('component', 'Component'),
        ('priority', 'Priority'),
        ('keywords', 'Keywords'),
        ('version', 'Version'),
        ('platform', 'Platform'),
        ('milestone', 'Milestone'),
        ('difficulty', 'Difficulty'),
        ('type', 'Type'),
        ('wip', 'Completion'),
        ('severity', 'Severity'),
    )

    type = 'ticket'

    def __init__(self, service, **kw):
        for k, v in kw.items():
            if not v:
                v = None
            setattr(self, k, v)

        self.comments = None
        self.attachments = None
        self.changes = None

        self.description = TracComment(
            count=0, creator=self.reporter, created=self.created,
            text=self.description.strip())


class Trac(Service):
    """Service supporting the Trac-based ticket trackers."""

    item = TracTicket
    item_endpoint = '/ticket/{id}'
    attachment = TracAttachment

    def __init__(self, max_results=None, **kw):
        # Trac uses a setting of 0 to disable paging search results
        if max_results is None:
            max_results = 0
        super().__init__(endpoint='/rpc', max_results=max_results, **kw)

    def login(self, **kw):
        # authenticated sessions use a different endpoint
        self._base = f"{self._base.rsplit('/')[0]}/login/rpc"
        super().login(**kw)

    def inject_auth(self, request, params):
        raise NotImplementedError

    @staticmethod
    def handle_error(code, msg):
        """Handle Trac specific errors."""
        raise TracError(msg=msg, code=code)


@req_cmd(Trac, cmd='search')
class _SearchRequest(ParseRequest, RPCRequest):
    """Construct a search request.

    Query docs:
        https://trac.edgewall.org/wiki/TracQuery
    """

    # map from standardized kwargs name to expected service parameter name
    _params_map = {
        'created': 'time',
        'modified': 'changetime',
        'sort': 'order',
    }

    def __init__(self, **kw):
        super().__init__(command='ticket.query', **kw)

    def parse(self, data):
        # Trac search requests return a list of matching IDs that we resubmit
        # via a multicall to grab ticket data if any matches exist.
        if data:
            tickets = self.service.GetItemRequest(ids=data).send()
            yield from tickets

    @aliased
    class ParamParser(ParseRequest.ParamParser):

        # Map of allowed sorting input values to service parameters.
        _sorting_map = {
            'assignee': 'owner',
            'id': 'id',
            'created': 'created',
            'modified': 'modified',
            'status': 'status',
            'description': 'description',
            'creator': 'reporter',
            'milestone': 'milestone',
            'component': 'component',
            'summary': 'summary',
            'priority': 'priority',
            'keywords': 'keywords',
            'version': 'version',
            'platform': 'platform',
            'difficulty': 'difficulty',
            'type': 'type',
            'wip': 'wip',
            'severity': 'severity',
        }

        def __init__(self, **kw):
            super().__init__(**kw)
            self.query = {}
            self._sort = {'order': 'id'}

        def _finalize(self, **kw):
            if not any((self.params, self.query)):
                raise BiteError('no supported search terms or options specified')

            # disable results paging
            self.params['max'] = self.service.max_results

            # default to sorting ascending by ID
            self.params.update(self._sort)

            # default to returning only open tickets
            if 'status' not in self.params:
                self.params['status'] = '!closed'

            # encode params into expected format
            params = (f'{k}={v}' for k, v in dict2tuples(self.params))

            # combine query/params values into a query string
            return '&'.join(chain(self.query.values(), params))

        def terms(self, k, v):
            or_queries = []
            display_terms = []
            for term in v:
                or_terms = [x.replace('"', '\\"') for x in term.split(',')]
                or_display_terms = [f'"{x}"' for x in or_terms]
                if len(or_terms) > 1:
                    or_queries.append('|'.join(or_terms))
                    display_terms.append(f"({' OR '.join(or_display_terms)})")
                else:
                    or_queries.append(or_terms[0])
                    display_terms.append(or_display_terms[0])
            # space-separated AND queries are only supported in 1.2.1 onwards
            # https://trac.edgewall.org/ticket/10152
            self.query['summary'] = f"summary~={' '.join(or_queries)}"
            self.options.append(f"Summary: {' AND '.join(display_terms)}")

        @alias('modified')
        def created(self, k, v):
            self.params[k] = f'{v.isoformat()}..'
            self.options.append(f'{k.capitalize()}: {v} (since {v.isoformat()})')

        def sort(self, k, v):
            if v[0] == '-':
                key = v[1:]
                desc = 1
            else:
                key = v
                desc = 0
            try:
                order_var = self._sorting_map[key]
            except KeyError:
                choices = ', '.join(sorted(self._sorting_map.keys()))
                raise BiteError(
                    f'unable to sort by: {key!r} (available choices: {choices}')
            self._sort['order'] = order_var
            if desc:
                self._sort['desc'] = desc
            self.options.append(f"Sort order: {v}")

        @alias('reporter')
        def owner(self, k, v):
            self.params[k] = '|'.join(v)
            self.options.append(f"{self.service.item.attributes[k]}: {', '.join(v)}")


@req_cmd(Trac)
class _GetItemRequest(Multicall):
    """Construct an item request."""

    def __init__(self, ids, **kw):
        super().__init__(command='ticket.get', params=ids, **kw)
        if ids is None:
            raise ValueError(f'No {self.service.item.type} ID(s) specified')

        self.ids = ids

    def parse(self, data):
        # unwrap multicall result
        data = super().parse(data)
        for item in data:
            id, created, modified, attrs = item
            yield self.service.item(
                self.service, id=id, created=created, modified=modified, **attrs)


@req_cmd(Trac, name='_ChangelogRequest')
class _ChangelogRequest(Multicall):
    """Construct a changelog request."""

    def __init__(self, ids=None, item_id=False, data=None, **kw):
        if data is None:
            super().__init__(command='ticket.changeLog', params=ids, **kw)
        else:
            Request.__init__(self, reqs=(NullRequest(),), **kw)

        if ids is None and data is None:
            raise ValueError(f'No ID(s) specified')

        self.ids = ids
        self._data = data

    @generator
    def parse(self, data):
        if self._data is not None:
            return self._data
        # unwrap multicall result
        return super().parse(data)


@req_cmd(Trac, cmd='comments')
class _CommentsRequest(_ChangelogRequest):
    """Construct a comments request."""

    def __init__(self, **kw):
        super().__init__(**kw)
        self.options.append(f"IDs: {', '.join(map(str, self.ids))}")

    def parse(self, data):
        # unwrap multicall result
        data = super().parse(data)
        for changes in data:
            l = []
            count = 1
            for change in changes:
                created, creator, field, old, new, perm = change
                if field == 'comment':
                    text = new.strip()
                    # skip comments without text or only whitespace
                    if text:
                        l.append(TracComment(
                            count=count, creator=creator, created=created, text=text))
                        count += 1
            yield tuple(l)


@req_cmd(Trac, cmd='attachments')
class _AttachmentsRequest(Multicall):
    """Construct an attachments request."""

    def __init__(self, ids, **kw):
        super().__init__(command='ticket.listAttachments', params=ids, **kw)
        if ids is None:
            raise ValueError(f'No {self.service.item.type} ID(s) specified')

        self.ids = ids

    def parse(self, data):
        # unwrap multicall result
        data = super().parse(data)
        for item_attachments in data:
            l = []
            for attachment in item_attachments:
                filename, description, size, created, creator = attachment
                l.append(TracAttachment(
                    creator=creator, created=created, size=size, filename=filename))
            yield tuple(l)


@req_cmd(Trac, cmd='changes')
class _ChangesRequest(_ChangelogRequest):
    """Construct a changes request."""

    _skip_fields = {'comment', 'attachment'}

    @generator
    def parse(self, data):
        data = super().parse(data)
        for changes in data:
            l = []
            count = 1
            prev_created = None
            changes_dct = {}
            for i, change in enumerate(changes):
                created, creator, field, old, new, perm = change
                if field not in self._skip_fields and any((old, new)):
                    changes_dct[field] = (old, new)
                    if prev_created and created != prev_created:
                        l.append(TracEvent(
                            id=i, count=count, creator=creator,
                            created=created, changes=changes_dct))
                        changes_dct = {}
                        count += 1
                    prev_created = created
            yield tuple(l)


@req_cmd(Trac, cmd='get')
class _GetRequest(MergedMulticall):
    """Construct requests to retrieve all known data for given ticket IDs."""

    def __init__(self, ids, get_comments=True, get_attachments=True,
                 get_changes=False, **kw):
        super().__init__(**kw)

        if not ids:
            raise ValueError('No {self.service.item.type} ID(s) specified')
        self.ids = ids

        reqs = [self.service.GetItemRequest(ids=ids)]
        if get_comments or get_changes:
            reqs.append(self.service._ChangelogRequest(ids=ids))
        if get_attachments:
            reqs.append(self.service.AttachmentsRequest(ids=ids))
        self.reqs = reqs

        self._get_comments = get_comments
        self._get_attachments = get_attachments
        self._get_changes = get_changes

    @property
    def _none_gen(self):
        for x in self.ids:
            yield None

    def parse(self, data):
        data = super().parse(data)
        items = next(data)
        if self._get_comments or self._get_changes:
            changelogs = next(data)
        if self._get_attachments:
            attachments = next(data)
        else:
            attachments = self._none_gen

        items = list(items)
        comments = self._none_gen
        changes = self._none_gen

        if self._get_comments or self._get_changes:
            changelogs = list(changelogs)
            if self._get_comments:
                item_descs = ((x.description,) for x in items)
                item_comments = self.service.comments(data=changelogs)
                comments = (x + y for x, y in zip(item_descs, item_comments))
            if self._get_changes:
                changes = self.service.changes(data=changelogs)

        for item in items:
            item.comments = next(comments)
            item.attachments = next(attachments)
            item.changes = next(changes)
            yield item

    def handle_exception(self, e):
        if e.code == 404:
            raise RequestError('nonexistent item ID', code=e.code)
        raise e


@req_cmd(Trac, cmd='version')
class _VersionRequest(RPCRequest):
    """Construct a version request."""

    def __init__(self, **kw):
        super().__init__(command='system.getAPIVersion', **kw)

    def parse(self, data):
        return '.'.join(map(str, data))
