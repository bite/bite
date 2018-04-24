from ._xml import Xml
from ._rest import REST


class XmlREST(Xml, REST):
    """Support generic XML-based REST services."""

    def __init__(self, **kw):
        super().__init__(**kw)
        self.session.headers.update({
            'Accept': 'application/xml',
            'Content-Type': 'application/xml'
        })

    @staticmethod
    def _encode_request(params=None):
        """Encode the data body for a request."""
        if params is None:
            params = {}
        return self.dumps({**params})

    @staticmethod
    def _decode_request(request):
        """Decode the data body of a request."""
        return self.loads(request.data)
