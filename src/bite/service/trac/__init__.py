"""Support Trac's RPC interface.

API docs:
    - https://trac-hacks.org/wiki/XmlRpcPlugin
    - https://trac.videolan.org/vlc/rpc
"""

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


@req_cmd(Trac, 'search')
class _SearchRequest(RPCRequest, ParseRequest):
    """Construct a search request."""

    def __init__(self, *args, **kw):
        super().__init__(command='ticket.query', **kw)

    def parse(self, data):
        # Trac search requests return a list of matching IDs that we resubmit
        # via a multicall to grab ticket data if any matches exist.
        if data:
            tickets = self.service.GetItemRequest(ids=data).send()
            yield from tickets

    class ParamParser(ParseRequest.ParamParser):

        def _finalize(self, **kw):
            if not self.params:
                raise BiteError('no supported search terms or options specified')

            # disable results paging
            self.params['max'] = self.service.max_results

            # default to sorting ascending by ID
            if 'order' not in self.params:
                self.params['order'] = 'id'

            # default to returning only open tickets
            if 'status' not in self.params:
                self.params['status'] = '!closed'

            # return params string
            return '&'.join(f'{k}={v}' for k, v in dict2tuples(self.params))

        def terms(self, k, v):
            self.params['summary'] = f'~{v[0]}'
            self.options.append(f"Summary: {', '.join(map(str, v))}")

        def created(self, k, v):
            self.params['time'] = f'{v.isoformat()}..'
            self.options.append(f'{self.service.item.attributes[k]}: {v} (since {v.isoformat()})')
        modified = created


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
