from xmlrpc.client import dumps, getparser, Fault
from xml.parsers.expat import ExpatError

from . import Service
from ..exceptions import RequestError, ParsingError


class Xmlrpc(Service):
    """Support generic XML-RPC services."""

    def __init__(self, **kw):
        super().__init__(**kw)
        self.session.headers.update({
            'Accept': 'text/xml',
            'Content-Type': 'text/xml'
        })

    def encode_request(self, method, params):
        """Encode the data body for an XML-RPC request."""
        encoding = 'utf-8'
        return dumps((params,), method, encoding=encoding,
                     allow_none=False).encode(encoding, 'xmlcharrefreplace')

    def parse_response(self, response):
        """Send request object and perform checks on the response."""
        try:
            return self._parse_xml(response)[0]
        except Fault as e:
            raise RequestError(msg=e.faultString, code=e.faultCode)

    @staticmethod
    def _parse_xml(response):
        """Parse XML data from response."""
        stream = _IterContent(response)

        p, u = getparser(use_datetime=True)

        while 1:
            data = stream.read(64*1024)
            if not data:
                break
            try:
                p.feed(data)
            except ExpatError as e:
                if not response.headers['Content-Type'].startswith('text/xml'):
                    raise RequestError('XML-RPC interface likely disabled on server')
                raise ParsingError(msg='failed parsing XML: {}'.format(str(e)))

        p.close()
        return u.close()


class _IterContent(object):

    def __init__(self, file, size=64*1024):
        self.initial = True
        self.chunks = file.iter_content(chunk_size=size)

    def read(self, size=64*1024):
        try:
            return next(self.chunks)
        except StopIteration:
            return b''
