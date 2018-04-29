from xmlrpc.client import dumps, loads, Unmarshaller, Fault, ResponseError

from snakeoil.klass import steal_docs

from . import Service
from ._reqs import RPCRequest
from ._xml import Xml
from ..exceptions import RequestError, ParsingError


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


class Xmlrpc(Xml):
    """Support generic XML-RPC services.

    Spec: http://xmlrpc.scripting.com/spec.html
    """

    @staticmethod
    @steal_docs(Service)
    def _encode_request(method, params=None):
        encoding = 'utf-8'
        if isinstance(params, (list, tuple)):
            params = tuple(params)
        else:
            params = (params,) if params is not None else ()
        return dumps(params, method, encoding=encoding,
                     allow_none=True).encode(encoding, 'xmlcharrefreplace')

    @staticmethod
    @steal_docs(Service)
    def _decode_request(request):
        params, method = loads(request.data)
        if not params:
            params = None
        else:
            params = params[0]
        return method, params

    @steal_docs(Service)
    def parse_response(self, response):
        try:
            data = super().parse_response(response)
        except Fault as e:
            raise RequestError(msg=e.faultString, code=e.faultCode)
        except ResponseError as e:
            raise ParsingError(msg='failed parsing XML') from e

        try:
            faults = data.get('faults', None)
        except AttributeError:
            faults = None

        if not faults:
            return data
        else:
            self.handle_error(code=faults[0]['faultCode'], msg=faults[0]['faultString'])

    def _getparser(self, unmarshaller=None):
        u = unmarshaller
        if u is None:
            u = _Unmarshaller(use_datetime=True)
        return super()._getparser(unmarshaller=u)


class Multicall(RPCRequest):
    """Construct a system.multicall request."""

    def __init__(self, method, params, *args, **kw):
        params = [[{'methodName': method, 'params': [x]} for x in params]]
        super().__init__(*args, command='system.multicall', params=params, **kw)

    def parse(self, data):
        for x in data:
            yield x[0]
