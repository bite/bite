"""Support Trac's XML-RPC interface."""

from dateutil.parser import parse as dateparse

from . import Trac, GetItemRequest
from .._xmlrpc import Xmlrpc, Multicall, _Unmarshaller
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