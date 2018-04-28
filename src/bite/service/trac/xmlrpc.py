"""Support Trac's XML-RPC interface."""

from . import Trac, GetItemRequest
from .._xmlrpc import Xmlrpc, Multicall
from .._reqs import req_cmd


class TracXmlrpc(Trac, Xmlrpc):

    _service = 'trac-xmlrpc'


@req_cmd(TracXmlrpc)
class _GetItemRequest(GetItemRequest, Multicall):
    """Construct a multicall issue request."""
