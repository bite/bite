"""Support Trac's JSON-RPC interface."""

from dateutil.parser import parse as dateparse

from . import (
    Trac, GetItemRequest, GetRequest, CommentsRequest, AttachmentsRequest,
    ChangesRequest, _ChangelogRequest,
)
from .._jsonrpc import Jsonrpc, Multicall, MergedMulticall
from .._reqs import req_cmd
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


@req_cmd(TracJsonrpc)
class _GetItemRequest(GetItemRequest, Multicall):
    """Construct a multicall issue request."""


@req_cmd(TracJsonrpc, cmd='get')
class _GetRequest(GetRequest, MergedMulticall):
    """Construct a multicall get request."""


@req_cmd(TracJsonrpc, name='_ChangelogRequest')
class _ChangelogRequest(_ChangelogRequest, Multicall):
    """Construct requests to retrieve all known data for given ticket IDs."""


@req_cmd(TracJsonrpc, cmd='comments')
class _CommentsRequest(CommentsRequest, Multicall):
    """Construct a multicall comments request."""


@req_cmd(TracJsonrpc, cmd='attachments')
class _AttachmentsRequest(AttachmentsRequest, Multicall):
    """Construct a multicall attachments request."""


@req_cmd(TracJsonrpc, cmd='changes')
class _ChangesRequest(ChangesRequest, Multicall):
    """Construct a multicall changes request."""
