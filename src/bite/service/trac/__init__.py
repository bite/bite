"""Support Trac's RPC interface.

API docs:
    - https://trac-hacks.org/wiki/XmlRpcPlugin
    - https://trac.videolan.org/vlc/rpc
"""

from itertools import chain

from .. import Service
from .._reqs import RPCRequest, Request, ParseRequest, req_cmd, generator
from ...exceptions import BiteError, RequestError
from ...objects import Item
from ...utils import dict2tuples


class TracError(RequestError):
    """Trac service specific error."""

    def __init__(self, msg, code=None, text=None):
        msg = f'Trac error: {msg}'
        super().__init__(msg, code, text)


class TracTicket(Item):

    attributes = {
    }

    attribute_aliases = {
        'title': 'summary',
    }

    _print_fields = (
        ('title', 'Title'),
        ('id', 'ID'),
        ('created', 'Reported'),
        ('modified', 'Updated'),
    )

    type = 'ticket'

    def __init__(self, service, **kw):
        for k, v in kw.items():
            setattr(self, k, v)


class Trac(Service):
    """Service supporting the Trac-based ticket trackers."""

    item = TracTicket
    item_endpoint = '/ticket/{id}'

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

    def __init__(self, *args, **kw):
        super().__init__(command='ticket.query', **kw)

    def parse(self, data):
        # Trac search requests return a list of matching IDs that we resubmit
        # via a multicall to grab ticket data if any matches exist.
        if data:
            tickets = self.service.GetItemRequest(ids=data).send()
            yield from tickets

    class ParamParser(ParseRequest.ParamParser):

        # Map of allowed sorting input values to service parameters.
        sorting_map = {
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

        def _finalize(self, **kw):
            if not any((self.params, self.query)):
                raise BiteError('no supported search terms or options specified')

            # disable results paging
            self.params['max'] = self.service.max_results

            # default to sorting ascending by ID
            if 'order' not in self.params:
                self.params['order'] = 'id'

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

        def created(self, k, v):
            self.params['time'] = f'{v.isoformat()}..'
            self.options.append(f'{self.service.item.attributes[k]}: {v} (since {v.isoformat()})')
        modified = created

        def order(self, k, v):
            if v[0] == '-':
                key = v[1:]
                desc = 1
            else:
                key = v
                desc = 0
            try:
                order_var = self.sorting_map[key]
            except KeyError:
                choices = ', '.join(sorted(self.sorting_map.keys()))
                raise BiteError(
                    f'unable to sort by: {key!r} (available choices: {choices}')
            self.params[k] = order_var
            if desc:
                self.params['desc'] = desc
            self.options.append(f"Sort order: {v}")

        def owner(self, k, v):
            self.params[k] = '|'.join(v)
            self.options.append(f"{self.service.item.attributes[k]}: {', '.join(v)}")
        reporter = owner


class GetItemRequest(Request):
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


@req_cmd(Trac, 'version')
class _VersionRequest(RPCRequest):
    """Construct a version request."""

    def __init__(self, *args, **kw):
        super().__init__(method='system.getAPIVersion', *args, **kw)

    def parse(self, data):
        return '.'.join(map(str, data))
