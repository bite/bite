from itertools import repeat, islice
from xmlrpc.client import dumps, loads, Unmarshaller, Fault, ResponseError

from snakeoil.klass import steal_docs

from . import Service
from ._reqs import RPCRequest
from ._xml import Xml
from ..exceptions import RequestError, ParsingError
from ..utils import nonstring_iterable


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


class XmlrpcError(RequestError):
    pass


class Xmlrpc(Xml):
    """Support generic XML-RPC services.

    Spec: http://xmlrpc.scripting.com/spec.html
    """

    @staticmethod
    @steal_docs(Service)
    def _encode_request(method, params=None):
        if isinstance(params, (list, tuple)):
            params = tuple(params)
        else:
            params = (params,) if params is not None else ()
        return dumps(params, method, encoding='utf-8',
                     allow_none=True).encode('utf-8', 'xmlcharrefreplace')

    @staticmethod
    @steal_docs(Service)
    def _decode_request(request):
        params, method = loads(request.data)
        params = params[0] if params else None
        return method, params

    @steal_docs(Service)
    def parse_response(self, response):
        try:
            data = super().parse_response(response)
        except Fault as e:
            raise XmlrpcError(msg=e.faultString, code=e.faultCode)
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
        u = _Unmarshaller(use_datetime=True) if unmarshaller is None else unmarshaller
        return super()._getparser(unmarshaller=u)

    def multicall(self, *args, **kw):
        return Multicall(service=self, *args, **kw)

    def merged_multicall(self, reqs, *args, **kw):
        return MergedMulticall(reqs=reqs, service=self, *args, **kw)


class MulticallIterator(object):
    """Iterate over the results of a multicall.

    Raising any XML-RPC faults that are found.
    """

    def __init__(self, results):
        self.results = tuple(results)
        self.idx = 0

    def __iter__(self):
        return self

    def __next__(self):
        try:
            item = self.results[self.idx]
        except IndexError:
            raise StopIteration

        if isinstance(item, dict):
            raise Fault(item['faultCode'], item['faultString'])
        elif isinstance(item, list):
            self.idx += 1
            return item[0]
        else:
            raise ValueError("unexpected type in multicall result")


class Multicall(RPCRequest):
    """Construct a system.multicall request."""

    def __init__(self, method, params, *args, **kw):
        methods = repeat(method) if isinstance(method, str) else method
        params = (tuple(x) if nonstring_iterable(x) else (x,) for x in params)
        params = tuple({'methodName': m, 'params': x} for m, x in zip(methods, params))
        super().__init__(*args, method='system.multicall', params=(params,), **kw)

    def parse(self, data):
        return MulticallIterator(data)


class MergedMulticall(RPCRequest):

    def __init__(self, reqs, *args, **kw):
        self.req_groups = []
        self.reqs = reqs

        params = []
        for req in reqs:
            params.extend(req.params[0])
            self.req_groups.append(len(req.params[0]))
        params = tuple(params)

        super().__init__(*args, method='system.multicall', params=(params,), **kw)

    def parse(self, data):
        start = 0
        for i, length in enumerate(self.req_groups):
            yield self.reqs[i].parse(islice(data, start, start + length))
            start += length
