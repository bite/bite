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

    def parse_response(self, response):
        try:
            return response.json()
        except json.decoder.JSONDecodeError as e:
            if not response.headers['Content-Type'].startswith('application/json'):
                raise RequestError('JSON-RPC interface likely disabled on server')
            raise ParsingError(msg='failed parsing JSON', text=str(e))
