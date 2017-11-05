from xmlrpc.client import dumps, loads, getparser, Fault, Unmarshaller
from xml.parsers.expat import ExpatError

from lxml.etree import XMLPullParser

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

    @staticmethod
    def _encode_request(method, params=None):
        """Encode the data body for an XML-RPC request."""
        encoding = 'utf-8'
        if isinstance(params, list):
            params = tuple(params)
        else:
            params = (params,) if params is not None else ()
        return dumps(params, method, encoding=encoding,
                     allow_none=True).encode(encoding, 'xmlcharrefreplace')

    @staticmethod
    def _decode_request(request):
        """Decode the data body of a request."""
        params, method = loads(request.data)
        if not params:
            params = None
        else:
            params = params[0]
        return method, params

    def parse_response(self, response):
        """Send request object and perform checks on the response."""
        try:
            return self._parse_xml(response)[0]
        except Fault as e:
            raise RequestError(msg=e.faultString, code=e.faultCode)

    def _getparser(self, use_datetime=True):
        return getparser(use_datetime=use_datetime)

    def _parse_xml(self, response):
        """Parse XML data from response."""
        stream = _IterContent(response)

        p, u = self._getparser(use_datetime=True)

        while 1:
            data = stream.read(64*1024)
            if not data:
                break
            try:
                p.feed(data)
            except ExpatError as e:
                if not response.headers['Content-Type'].startswith('text/xml'):
                    raise RequestError('XML-RPC interface likely disabled on server')
                raise ParsingError(msg='failed parsing XML', text=str(e))

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


class _LXMLParser(object):
    """XML parser using lxml."""

    def __init__(self, target):
        self._parser = XMLPullParser(events=('start', 'end'), recover=True)
        self._target = target

    def handle_events(self):
        for action, element in self._parser.read_events():
            if action == 'start':
                self._target.start(element.tag, element.attrib)
            elif action == 'end':
                if element.text:
                    self._target.data(element.text)
                self._target.end(element.tag)
                element.clear()

    def feed(self, data):
        try:
            self._parser.feed(data)
        except:
            raise
        self.handle_events()

    def close(self):
        self._parser.close()


class _Unmarshaller(Unmarshaller):
    """Override to avoid decoding unicode objects.

    This can be dropped once the upstream xmlrpc.client lib is fixed.
    """

    def end_string(self, data):
        if self._encoding and not isinstance(data, str):
            data = data.decode(self._encoding)
        self.append(data)
        self._value = 0
    Unmarshaller.dispatch["string"] = end_string
    Unmarshaller.dispatch["name"] = end_string # struct keys are always strings


class LxmlXmlrpc(Xmlrpc):
    """Support generic XML-RPC services using lxml."""

    def _getparser(self, use_datetime=True):
        u = _Unmarshaller(use_datetime=use_datetime)
        p = _LXMLParser(u)
        return p, u
