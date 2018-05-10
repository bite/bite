from urllib.parse import urlencode

from . import Service
from ._reqs import Request
from ..utils import dict2tuples


class REST(Service):
    """Support generic REST-based services."""

    def _failed_http_response(self, response):
        # catch invalid REST API resource requests
        if response.status_code in (400, 404):
            self.parse_response(response)
        super()._failed_http_response(response)


class RESTRequest(Request):
    """Construct a REST request."""

    def __init__(self, service, endpoint=None, method='GET', **kw):
        self.method = method
        if endpoint is None:
            endpoint = service._base.rstrip('/')
        elif endpoint.startswith('/'):
            endpoint = f"{service._base.rstrip('/')}{endpoint}"
        self.endpoint = endpoint
        self.data = {}
        super().__init__(service, method=method, **kw)

    @property
    def url(self):
        """Construct a full resource URL with params encoded."""
        params = list(dict2tuples(self.params))
        params_str = f'?{urlencode(params)}' if params else ''
        return f"{self.endpoint}{params_str}"

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
