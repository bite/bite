from xmlrpc.client import getparser, Unmarshaller
from xml.parsers.expat import ExpatError

from lxml.etree import XMLPullParser, XMLSyntaxError
from snakeoil.klass import steal_docs

from . import Service
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
        try:
            return self._parse_xml(response)[0]
        except (ExpatError, XMLSyntaxError) as e:
            # The default XML parser in python (expat) has issues with badly
            # formed XML. This is alleviated somewhat by providing an
            # alternative class that uses lxml for parsing which allows
            # recovering from certain types of broken XML.
            if not response.headers['Content-Type'].startswith('text/xml'):
                msg = 'non-XML response from server'
                if not self.verbose:
                    msg += ' (use verbose mode to see it)'
                raise RequestError(msg=msg, text=response.text)
            raise ParsingError(msg='failed parsing XML', text=str(e)) from e

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
            p.feed(data)
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
    """XML parser using lxml.

    That tries hard to parse through broken XML.
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


class LxmlXml(Xml):
    """Use lxml for parsing with XML-based services."""

    def _getparser(self, use_datetime=True):
        u = _Unmarshaller(use_datetime=use_datetime)
        p = _LXMLParser(u)
        return p, u
