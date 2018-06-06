import lxml.html
from snakeoil.klass import steal_docs

from . import Service
from ._reqs import URLRequest
from ..exceptions import RequestError


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


class HTMLRequest(URLRequest):
    """Construct an HTML request."""

    def parse_response(self, response):
        return lxml.html.fromstring(response.text)
