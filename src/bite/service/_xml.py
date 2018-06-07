import io

from lxml.etree import XMLPullParser, XMLSyntaxError, parse as parse_xml
from snakeoil.klass import steal_docs

from . import Service
from ._reqs import URLRequest
from ..exceptions import ParsingError, RequestError


class Xml(Service):
    """Support generic services that use XML to communicate."""

    def __init__(self, **kw):
        super().__init__(**kw)
        self.session.headers.update({
            'Accept': 'text/xml',
            'Content-Type': 'text/xml'
        })

    @steal_docs(Service)
    def parse_response(self, response):
        if not response.headers.get('Content-Type', '').startswith('text/xml'):
            msg = 'non-XML response from server'
            if not self.verbose:
                msg += ' (use verbose mode to see it)'
            raise RequestError(
                msg, code=response.status_code, text=response.text, response=response)
        try:
            return self._parse_xml(response)[0]
        except XMLSyntaxError as e:
            raise ParsingError(msg='failed parsing XML') from e

    def _getparser(self, unmarshaller=None):
        u = unmarshaller if unmarshaller is not None else UnmarshallToDict()
        p = LXMLParser(u)
        return p, u

    def _parse_xml(self, response):
        """Parse XML data from response."""
        stream = _IterContent(response)

        p, u = self._getparser()

        while 1:
            data = stream.read(64*1024)
            if not data:
                break
            p.feed(data)
        p.close()

        return u.close()

    def dumps(self, s):
        """Encode dictionary object to XML."""
        raise NotImplementedError

    def loads(self, s):
        """Decode XML to dictionary object."""
        raise NotImplementedError


class XMLRequest(URLRequest):
    """Construct a XML request."""

    def parse_response(self, response):
        """Parse the raw XML content."""
        # Requesting the text content of the response doesn't remove the BOM so
        # we request the binary content and decode it ourselves to remove it.
        f = io.StringIO(response.content.decode('utf-8-sig'))
        return parse_xml(f)


class _IterContent(object):

    def __init__(self, file, size=64*1024):
        self.initial = True
        self.chunks = file.iter_content(chunk_size=size)

    def read(self, size=64*1024):
        try:
            return next(self.chunks)
        except StopIteration:
            return b''


class LXMLParser(object):
    """XML parser using lxml.

    The default XML parser in python based on expat has issues with badly
    formed XML. We workaround this somewhat by using lxml for parsing which
    allows recovering from certain types of broken XML.
    """

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


# TODO: implement this for XML REST clients
class UnmarshallToDict(object):
    pass
