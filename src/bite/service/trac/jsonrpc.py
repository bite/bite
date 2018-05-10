"""Support Trac's JSON-RPC interface."""

from dateutil.parser import parse as dateparse

from . import Trac
from .._jsonrpc import Jsonrpc
from ...utc import utc


def as_datetime(dct):
    """Decode datetime objects in data responses while decoding json."""
    try:
        type, val = dct['__jsonclass__']
        if type == 'datetime':
            # trac doesn't specify an offset for its timestamps, assume UTC
            return dateparse(val).astimezone(utc)
    except KeyError:
        return dct


class TracJsonrpc(Trac, Jsonrpc):

    _service = 'trac-jsonrpc'

    def parse_response(self, response):
        return super().parse_response(response, object_hook=as_datetime)
