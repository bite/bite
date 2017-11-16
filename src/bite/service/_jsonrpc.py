try: import simplejson as json
except ImportError: import json

from ._json import Json


class Jsonrpc(Json):
    """Support generic JSON-RPC services."""

    @staticmethod
    def _encode_request(method, params=None, **kw):
        """Encode the data body for a JSON-RPC request."""
        if params is None:
            params = {}
        return json.dumps({'method': method, 'params': [params], **kw})

    @staticmethod
    def _decode_request(request):
        """Decode the data body of a request."""
        data = json.loads(request.data)
        params = data['params']
        method = data['method']
        return method, params
