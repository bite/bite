from itertools import repeat, islice
try: import simplejson as json
except ImportError: import json

from snakeoil.klass import steal_docs

from . import Service
from ._json import Json
from ._reqs import RPCRequest
from ..utils import nonstring_iterable


class Jsonrpc(Json):
    """Support generic JSON-RPC 1.0 services.

    Spec: http://www.jsonrpc.org/specification_v1
    """

    @staticmethod
    @steal_docs(Service)
    def _encode_request(method, params=None, id=0):
        if isinstance(params, (list, tuple)):
            params = tuple(params)
        else:
            params = (params,) if params is not None else ()

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

    def multicall(self, *args, **kw):
        return Multicall(service=self, *args, **kw)

    def merged_multicall(self, reqs, *args, **kw):
        return MergedMulticall(reqs=reqs, service=self, *args, **kw)


class Multicall(RPCRequest):
    """Construct a system.multicall request."""

    def __init__(self, method, params, *args, **kw):
        methods = repeat(method) if isinstance(method, str) else method
        params = (tuple(x) if nonstring_iterable(x) else (x,) for x in params)
        params = tuple({'method': m, 'params': x} for m, x in zip(methods, params))
        super().__init__(*args, method='system.multicall', params=params, **kw)

    def parse(self, data):
        # TODO: refactor send/parsing to drop this hack
        if isinstance(data, dict):
            data = [data]

        for x in data:
            yield x['result']


class MergedMulticall(RPCRequest):

    def __init__(self, reqs, *args, **kw):
        self.req_groups = []
        self.reqs = reqs

        params = []
        for req in reqs:
            params.extend(req.params)
            self.req_groups.append(len(req.params))
        params = tuple(params)

        super().__init__(*args, method='system.multicall', params=params, **kw)

    def parse(self, data):
        start = 0
        for i, length in enumerate(self.req_groups):
            yield self.reqs[i].parse(islice(data, start, start + length))
            start += length
