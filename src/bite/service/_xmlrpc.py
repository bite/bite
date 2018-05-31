from xmlrpc.client import dumps, loads, Unmarshaller, Fault, ResponseError

from snakeoil.klass import steal_docs

from . import Service
from ._rpc import Rpc
from ._xml import Xml
from ..exceptions import ParsingError, RequestError


class _Unmarshaller(Unmarshaller):
    """Override to avoid decoding unicode objects.

    This can be dropped once the upstream xmlrpc.client lib is fixed.
    """
    dispatch = Unmarshaller.dispatch

    def end_string(self, data):
        if self._encoding and not isinstance(data, str):
            data = data.decode(self._encoding)
        self.append(data)
        self._value = 0
    dispatch["string"] = end_string
    dispatch["name"] = end_string # struct keys are always strings


class MulticallIterator(object):
    """Iterate over the results of a multicall.

    Raising any XML-RPC faults that are found.
    """

    def __init__(self, results, service):
        self.results = tuple(results)
        self.service = service
        self.idx = 0

    def __iter__(self):
        return self

    def __next__(self):
        try:
            item = self.results[self.idx]
        except IndexError:
            raise StopIteration

        if isinstance(item, dict):
            self.handle_error(item)
        elif isinstance(item, list):
            self.idx += 1
            return item[0]
        else:
            raise TypeError(f"unexpected multicall result: {item!r}")

    def handle_error(self, item):
        if 'faultCode' in item:
            raise self.service._service_error_cls(
                code=item['faultCode'], msg=item['faultString'])
        else:
            raise ValueError(f'unknown error object: {item}')


class Xmlrpc(Xml, Rpc):
    """Support generic XML-RPC services.

    Spec: http://xmlrpc.scripting.com/spec.html
    """

    _multicall_method = 'methodName'
    _multicall_iter = MulticallIterator

    @steal_docs(Service)
    def _encode_request(self, method, params=None):
        if isinstance(params, (list, tuple)):
            params = tuple(params)
        else:
            params = self._encode_params(params)
        try:
            return dumps(params, method, encoding='utf-8',
                         allow_none=True).encode('utf-8', 'xmlcharrefreplace')
        except OverflowError as e:
            raise RequestError('ID value exceeds XML-RPC limits')

    @steal_docs(Service)
    def _decode_request(self, request):
        params, method = loads(request.data)
        return method, self._extract_params(params)

    @staticmethod
    def _extract_params(params):
        return params[0] if params else params

    @staticmethod
    def _encode_params(params):
        return (params,) if params is not None else ()

    @steal_docs(Service)
    def parse_response(self, response):
        try:
            data = super().parse_response(response)
        except Fault as e:
            raise self._service_error_cls(msg=e.faultString, code=e.faultCode)
        except ResponseError as e:
            raise ParsingError(msg='failed parsing XML') from e

        try:
            faults = data.get('faults')
        except AttributeError:
            faults = None

        if not faults:
            return data
        else:
            self.handle_error(code=faults[0]['faultCode'], msg=faults[0]['faultString'])

    def _getparser(self, unmarshaller=None):
        u = _Unmarshaller(use_datetime=True) if unmarshaller is None else unmarshaller
        return super()._getparser(unmarshaller=u)
