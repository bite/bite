from multidict import MultiDict

from . import Service
from ._html import URLRequest
from ._reqs import ParseRequest


class REST(Service):
    """Support generic REST-based services."""

    def _failed_http_response(self, response):
        # catch invalid REST API resource requests
        if response.status_code in (400, 404):
            self.parse_response(response)
        super()._failed_http_response(response)


class RESTRequest(URLRequest):
    """Construct a REST request."""

    def __init__(self, **kw):
        super().__init__(**kw)
        self.data = {}

    def params_to_data(self):
        """Convert params to encoded request data."""
        self.data.update(self.params)
        self.params = {}

    def _finalize(self):
        """Set the request URL using the specified params and encode the data body."""
        # inject auth params if available
        super()._finalize()

        # construct URL to resource with requested params
        if self.method == 'GET':
            self._req.url = self.url
        else:
            self._req.url = self.endpoint
            self.params_to_data()

        # encode additional params to data body
        if self.data:
            self._req.data = self.service._encode_request(self.data)


class RESTParseRequest(ParseRequest):

    def __init__(self, **kw):
        initial_params = MultiDict()
        super().__init__(initial_params=initial_params, **kw)
