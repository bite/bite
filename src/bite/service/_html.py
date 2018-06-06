from urllib.parse import urlencode

import lxml.html
from multidict import MultiDict
from snakeoil.klass import steal_docs

from . import Service
from ._reqs import Request
from ..exceptions import RequestError
from ..utils import dict2tuples


class HTML(Service):
    """Support generic webscraping services."""

    @steal_docs(Service)
    def parse_response(self, response, **kw):
        if not response.headers.get('Content-Type', '').startswith('text/html'):
            msg = 'non-HTML response from server'
            if not self.verbose:
                msg += ' (use verbose mode to see it)'
            raise RequestError(
                msg, code=response.status_code, text=response.text, response=response)
        return lxml.html.fromstring(response.text)


class URLRequest(Request):
    """Construct a basic URL request."""

    def __init__(self, service, method='GET', endpoint=None, params=None, **kw):
        if endpoint is None:
            endpoint = service._base.rstrip('/')
        elif endpoint.startswith('/'):
            endpoint = f"{service._base.rstrip('/')}{endpoint}"
        self.endpoint = endpoint
        params = params if params is not None else MultiDict()
        super().__init__(service=service, method=method, params=params, **kw)

    def encode_params(self, params=None):
        params = params if params is not None else self.params
        return urlencode(tuple(dict2tuples(params)))

    @property
    def url(self):
        """Construct a full resource URL with params encoded."""
        params = self.encode_params()
        params_str = f'?{params}' if params else ''
        return f"{self.endpoint}{params_str}"

    def _finalize(self):
        """Set the request URL using the specified params and encode the data body."""
        # inject auth params if available
        super()._finalize()
        # construct URL to resource with requested params
        self._req.url = self.url


class HTMLRequest(URLRequest):
    """Construct an HTML request."""

    def parse_response(self, response):
        return lxml.html.fromstring(response.text)
