try: import simplejson as json
except ImportError: import json

from ._json import Json


class Jsonrpc(Json):
    """Support generic JSON-RPC 1.0 services.

    Spec: http://www.jsonrpc.org/specification_v1
    """

    @staticmethod
    def _encode_request(method, params, id=0):
        """Encode the data body for a JSON-RPC request."""
        data = {
            'method': method,
            'params': [params if params is not None else {}],
            'id': id,
        }
        return json.dumps(data)

    @staticmethod
    def _decode_request(request):
        """Decode the data body of a request."""
        data = json.loads(request.data)
        params = data['params']
        method = data['method']
        id = data['id']
        return method, params, id

    def parse_response(self, response):
        data = super().parse_response(response)
        error = data.get('error', None)
        if error is None:
            return data['result']
        else:
            self.handle_error(error)
