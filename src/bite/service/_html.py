import lxml.html
from snakeoil.klass import steal_docs

from . import Service
from ..exceptions import ParsingError, RequestError


class HTML(Service):
    """Support generic webscraping services."""

    @steal_docs(Service)
    def parse_response(self, response, **kw):
        if not response.headers.get('Content-Type', '').startswith('text/html'):
            msg = 'non-HTML response from server'
            if not self.verbose:
                msg += ' (use verbose mode to see it)'
            raise RequestError(code=response.status_code, msg=msg, text=response.text)
        return lxml.html.fromstring(response.text)
