"""Support Trac's RPC interface.

API docs:
    - https://trac-hacks.org/wiki/XmlRpcPlugin
    - https://trac.videolan.org/vlc/rpc
"""

from itertools import chain

from snakeoil.klass import aliased, alias

from .. import Service
from .._reqs import RPCRequest, Request, ParseRequest, NullRequest, req_cmd, generator
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

    def __init__(self, *args, max_results=None, **kw):
        # Trac uses a setting of 0 to disable paging search results
        if max_results is None:
            max_results = 0
        super().__init__(*args, endpoint='/rpc', max_results=max_results, **kw)

    def login(self, *args, **kw):
        # authenticated sessions use a different endpoint
        self._base = f"{self._base.rsplit('/')[0]}/login/rpc"
        super().login(*args, **kw)

    def inject_auth(self, request, params):
        raise NotImplementedError

    @staticmethod
    def handle_error(code, msg):
        """Handle Trac specific errors."""
        raise TracError(msg=msg, code=code)


@req_cmd(Trac, cmd='search')
class _SearchRequest(RPCRequest, ParseRequest):
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

    def __init__(self, *args, **kw):
        super().__init__(*args, method='ticket.query', **kw)

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

        def __init__(self, request):
            super().__init__(request)
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


class GetItemRequest(RPCRequest):
    """Construct an item request."""

    def __init__(self, ids, service, **kw):
        if ids is None:
            raise ValueError(f'No {service.item.type} ID(s) specified')

        super().__init__(service=service, method='ticket.get', params=ids, **kw)
        self.ids = ids

    def parse(self, data):
        # unwrap multicall result
        data = super().parse(data)
        for item in data:
            id, created, modified, attrs = item
            yield self.service.item(
                self.service, id=id, created=created, modified=modified, **attrs)


class _ChangelogRequest(Request):
    """Construct a changelog request."""

    def __init__(self, service, ids=None, item_id=False, data=None, **kw):
        if ids is None and data is None:
            raise ValueError(f'No ID(s) specified')
        options = []

        if data is None:
            super().__init__(service=service, method='ticket.changeLog', params=ids, **kw)
        else:
            Request.__init__(self, service=service, reqs=(NullRequest(),))

        self.options = options
        self.ids = ids
        self._data = data

    @generator
    def parse(self, data):
        if self._data is not None:
            return self._data
        # unwrap multicall result
        return super().parse(data)


class CommentsRequest(_ChangelogRequest):
    """Construct a comments request."""

    @generator
    def parse(self, data):
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


class AttachmentsRequest(RPCRequest):
    """Construct an attachments request."""

    def __init__(self, ids, service, **kw):
        if ids is None:
            raise ValueError(f'No {service.item.type} ID(s) specified')

        super().__init__(service=service, method='ticket.listAttachments', params=ids, **kw)
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


class ChangesRequest(_ChangelogRequest):
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


class GetRequest(Request):
    """Construct requests to retrieve all known data for given ticket IDs."""

    def __init__(self, ids, service, get_comments=False, get_attachments=False,
                 get_changes=False, *args, **kw):
        if not ids:
            raise ValueError('No {service.item.type} ID(s) specified')

        reqs = [service.GetItemRequest(ids=ids)]
        if get_comments or get_changes:
            reqs.append(service._ChangelogRequest(ids=ids))
        if get_attachments:
            reqs.append(service.AttachmentsRequest(ids=ids))

        super().__init__(service=service, reqs=reqs)
        self.ids = ids
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

    def __init__(self, *args, **kw):
        super().__init__(method='system.getAPIVersion', *args, **kw)

    def parse(self, data):
        return '.'.join(map(str, data))
