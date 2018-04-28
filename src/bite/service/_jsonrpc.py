try: import simplejson as json
except ImportError: import json

from snakeoil.klass import steal_docs

from . import Service
from ._json import Json


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
            params = [params] if params is not None else [{}]

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
    def parse_response(self, response):
        data = super().parse_response(response)
        error = data.get('error', None)
        if error is None:
            return data['result']
        else:
            # assume error object follows json-rpc 2.0 spec formatting
            self.handle_error(code=error['code'], msg=error['message'])
