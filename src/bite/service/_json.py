try: import simplejson as json
except ImportError: import json

from snakeoil.klass import steal_docs

from . import Service
from ..exceptions import ParsingError, RequestError


class Json(Service):
    """Support generic services that use JSON to communicate."""

    def __init__(self, **kw):
        super().__init__(**kw)
        self.session.headers.update({
            'Accept': 'application/json',
            'Content-Type': 'application/json'
        })

    @steal_docs(Service)
    def parse_response(self, response):
        if not response.headers.get('Content-Type', '').startswith('application/json'):
            msg = 'non-JSON response from server'
            if not self.verbose:
                msg += ' (use verbose mode to see it)'
            raise RequestError(msg=msg, text=response.text)
        try:
            return response.json()
        except json.decoder.JSONDecodeError as e:
            raise ParsingError(msg='failed parsing JSON', text=str(e))
