try: import simplejson as json
except ImportError: import json

from snakeoil.klass import steal_docs

from . import Service
from ._json import Json
from ._rpc import Rpc


class MulticallIterator(object):
    """Iterate over the results of a multicall."""

    def __init__(self, results):
        # TODO: refactor send/parsing to drop this hack
        if isinstance(results, dict):
            results = (results,)
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
            self.idx += 1
            return item['result']
        else:
            raise TypeError(f"unexpected multicall result: {item!r}")


class Jsonrpc(Json, Rpc):
    """Support generic JSON-RPC 1.0 services.

    Spec: http://www.jsonrpc.org/specification_v1
    """

    _multicall_iter = MulticallIterator

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
        error = data.get('error')
        if error is None:
            return data['result']
        else:
            # assume error object follows json-rpc 2.0 spec formatting
            self.handle_error(code=error['code'], msg=error['message'])
