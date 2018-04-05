try: import simplejson as json
except ImportError: import json

from ._json import Json


class JsonREST(Json):
    """Support generic JSON-based REST services."""

    @staticmethod
    def _encode_request(params=None):
        """Encode the data body for a request."""
        if params is None:
            params = {}
        return json.dumps({**params})

    @staticmethod
    def _decode_request(request):
        """Decode the data body of a request."""
        return json.loads(request.data)
