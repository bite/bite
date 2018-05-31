"""Support Trac's XML-RPC interface."""

from dateutil.parser import parse as dateparse

from . import Trac
from .._xmlrpc import Xmlrpc, MulticallIterator, _Unmarshaller
from ...utc import utc


class _Unmarshaller_UTC(_Unmarshaller):
    """Unmarshaller that assumes datetimes are in UTC."""

    dispatch = _Unmarshaller.dispatch

    def end_dateTime(self, data):
        value = dateparse(data).astimezone(utc)
        self.append(value)
    dispatch["dateTime.iso8601"] = end_dateTime


class TracMulticallIterator(MulticallIterator):
    """Iterate over the results of a multicall.

    Extract error message from Trac XML-RPC specific field.
    """

    def handle_error(self, item):
        if '_message' in item:
            raise self.service._service_error_cls(msg=item['_message'])
        else:
            super().handle_error(item)


class TracXmlrpc(Trac, Xmlrpc):

    _service = 'trac-xmlrpc'
    _multicall_iter = TracMulticallIterator

    def _getparser(self):
        u = _Unmarshaller_UTC()
        return super()._getparser(unmarshaller=u)
