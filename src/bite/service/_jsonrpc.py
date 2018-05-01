from collections import Iterable
from itertools import repeat
try: import simplejson as json
except ImportError: import json

from snakeoil.klass import steal_docs

from . import Service
from ._json import Json
from ._reqs import RPCRequest


class Jsonrpc(Json):
    """Support generic JSON-RPC 1.0 services.

    Spec: http://www.jsonrpc.org/specification_v1
    """

    @staticmethod
    @steal_docs(Service)
    def _encode_request(method, params=None, id=0):
        if isinstance(params, (list, tuple)):
            params = list(params)
        else:
            params = [params] if params is not None else []

        data = {
            'method': method,
            'params': params,
            'id': id,
        }
        return json.dumps(data)

    @staticmethod
    @steal_docs(Service)
    def _decode_request(request):
        data = json.loads(request.data)
        params = data['params']
        method = data['method']
        id = data['id']
        return method, params, id

    @steal_docs(Service)
    def parse_response(self, response, **kw):
        data = super().parse_response(response, **kw)
        error = data.get('error', None)
        if error is None:
            return data['result']
        else:
            # assume error object follows json-rpc 2.0 spec formatting
            self.handle_error(code=error['code'], msg=error['message'])


class Multicall(RPCRequest):
    """Construct a system.multicall request."""

    def __init__(self, method, params, *args, **kw):
        methods = repeat(method) if isinstance(method, str) else method
        params = (list(x) if isinstance(x, Iterable) else [x] for x in params)
        params = [{'method': m, 'params': x} for m, x in zip(methods, params)]
        super().__init__(*args, command='system.multicall', params=params, **kw)

    def parse(self, data):
        for x in data:
            yield x['result']
