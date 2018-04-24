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

    def _failed_http_response(self, response):
        # catch invalid REST API resource requests
        if response.status_code in (404,):
            self.parse_response(response)
        super()._failed_http_response(response)
