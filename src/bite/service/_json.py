try: import simplejson as json
except ImportError: import json

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

    def parse_response(self, response, **kw):
        """Parse the returned response."""
        if not response.headers.get('Content-Type', '').startswith('application/json'):
            msg = 'non-JSON response from server'
            if not self.verbose:
                msg += ' (use verbose mode to see it)'
            raise RequestError(
                msg, code=response.status_code, text=response.text, response=response)
        try:
            return response.json(**kw)
        except json.decoder.JSONDecodeError as e:
            # check for missing data content
            if not response.text.strip():
                raise ParsingError('no response content returned')
            msg = f'failed parsing JSON: {e}'
            raise ParsingError(msg=msg, text=response.text)
