try: import simplejson as json
except ImportError: import json

from . import Service
from ..exceptions import RequestError


class Jsonrpc(Service):
    """Support generic JSON-RPC services."""

    def __init__(self, **kw):
        super().__init__(**kw)
        self.session.headers.update({
            'Accept': 'application/json',
            'Content-Type': 'application/json'
        })

    def encode_request(self, method, params, **kw):
        """Encode the data body for a JSON-RPC request."""
        return json.dumps({'method': method, 'params': [params], **kw})

    def parse_response(self, response):
        try:
            return response.json()
        except json.decoder.JSONDecodeError as e:
            raise RequestError('error decoding response, JSON-RPC interface likely disabled on server')
