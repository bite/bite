"""Support Trac's JSON-RPC interface."""

from dateutil.parser import parse as dateparse

from . import Trac, GetItemRequest
from .._jsonrpc import Jsonrpc, Multicall
from .._reqs import req_cmd
from ...utc import utc


def as_datetime(dct):
    """Decode datetime objects in data responses while decoding json."""
    if '__jsonclass__' in dct:
        type, val = dct['__jsonclass__']
        if type == 'datetime':
            # trac doesn't specify an offset for its timestamps, assume UTC
            return dateparse(val).astimezone(utc)
    return dct


class TracJsonrpc(Trac, Jsonrpc):

    _service = 'trac-jsonrpc'

    def parse_response(self, response):
        return super().parse_response(response, object_hook=as_datetime)


@req_cmd(TracJsonrpc)
class _GetItemRequest(GetItemRequest, Multicall):
    """Construct a multicall issue request."""
