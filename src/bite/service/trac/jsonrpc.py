"""Support Trac's JSON-RPC interface."""

from . import Trac, GetItemRequest
from .._jsonrpc import Jsonrpc, Multicall
from .._reqs import req_cmd


class TracJsonrpc(Trac, Jsonrpc):

    _service = 'trac-jsonrpc'


@req_cmd(TracJsonrpc)
class _GetItemRequest(GetItemRequest, Multicall):
    """Construct a multicall issue request."""
