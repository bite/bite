"""Support Trac's XML-RPC interface."""

from dateutil.parser import parse as dateparse

from . import (
    Trac, GetItemRequest, GetRequest, CommentsRequest, AttachmentsRequest,
    ChangesRequest, _ChangelogRequest,
)
from .._xmlrpc import Xmlrpc, Multicall, MergedMulticall, _Unmarshaller
from .._reqs import req_cmd
from ...utc import utc


class _Unmarshaller_UTC(_Unmarshaller):
    """Unmarshaller that assumes datetimes are in UTC."""

    dispatch = _Unmarshaller.dispatch

    def end_dateTime(self, data):
        value = dateparse(data).astimezone(utc)
        self.append(value)
    dispatch["dateTime.iso8601"] = end_dateTime


class TracXmlrpc(Trac, Xmlrpc):

    _service = 'trac-xmlrpc'

    def _getparser(self):
        u = _Unmarshaller_UTC()
        return super()._getparser(unmarshaller=u)


@req_cmd(TracXmlrpc)
class _GetItemRequest(GetItemRequest, Multicall):
    """Construct a multicall issue request."""


@req_cmd(TracXmlrpc, cmd='get')
class _GetRequest(GetRequest, MergedMulticall):
    """Construct a multicall get request."""


@req_cmd(TracXmlrpc, name='_ChangelogRequest')
class _ChangelogRequest(_ChangelogRequest, Multicall):
    """Construct requests to retrieve all known data for given ticket IDs."""


@req_cmd(TracXmlrpc, cmd='comments')
class _CommentsRequest(CommentsRequest, Multicall):
    """Construct a multicall comments request."""


@req_cmd(TracXmlrpc, cmd='attachments')
class _AttachmentsRequest(AttachmentsRequest, Multicall):
    """Construct a multicall attachments request."""


@req_cmd(TracXmlrpc, cmd='changes')
class _ChangesRequest(ChangesRequest, Multicall):
    """Construct a multicall changes request."""
