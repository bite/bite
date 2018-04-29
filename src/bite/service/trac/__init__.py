"""Support Trac's RPC interface.

API docs:
    - https://trac-hacks.org/wiki/XmlRpcPlugin
    - https://trac.videolan.org/vlc/rpc
"""

from .._reqs import RPCRequest, Request, req_cmd
from .. import Service
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

    def inject_auth(self, request, params):
        raise NotImplementedError

    @staticmethod
    def handle_error(code, msg):
        """Handle Trac specific errors."""
        raise TracError(msg=msg, code=code)


@req_cmd(Trac, 'search')
class _SearchRequest(RPCRequest):
    """Construct a search request."""

    def __init__(self, service, **kw):
        params, options = self.parse_params(service=service, **kw)
        if not params:
            raise BiteError('no supported search terms or options specified')

        # disable results paging
        params['max'] = service.max_results

        # default to sorting ascending by ID
        if 'order' not in params:
            params['order'] = 'id'

        # default to returning only open tickets
        if 'status' not in params:
            params['status'] = '!closed'

        # create params string
        params_str = '&'.join(f'{k}={v}' for k, v in dict2tuples(params))

        super().__init__(service=service, command='ticket.query', params=params_str, **kw)
        self.options = options

    def parse_params(self, service, params=None, options=None, **kw):
        options = options if options is not None else []
        params = {}

        for k, v in ((k, v) for (k, v) in kw.items() if v):
            if k == 'terms':
                params['summary'] = f'~{v[0]}'
                options.append(f"Summary: {', '.join(map(str, v))}")

        return params, options

    def parse(self, data):
        # Trac search requests return a list of matching IDs that we resubmit
        # via a multicall to grab ticket data.
        tickets = self.service.GetItemRequest(ids=data).send()
        yield from tickets


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
