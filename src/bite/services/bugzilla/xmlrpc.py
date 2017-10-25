from xmlrpc.client import dumps, getparser

from . import Bugzilla, BugzillaAttachment
from ...objects import decompress
from ...exceptions import RequestError, AuthError


class BugzillaXmlrpc(Bugzilla):
    """Support Bugzilla's deprecated XML-RPC interface."""

    def __init__(self, **kw):
        self.endpoint = '/xmlrpc.cgi'
        super().__init__(**kw)
        self.session.headers.update({
            'Accept': 'text/xml',
            'Content-Type': 'text/xml'
        })
        self.attachment = BugzillaAttachmentXml

    def encode_request(self, method, params=None):
        """Encode the data body for an XML-RPC request."""
        if self.auth_token is not None:
            # TODO: Is there a better way to determine the difference between
            # tokens and API keys?
            if len(self.auth_token) > 16:
                params['Bugzilla_api_key'] = self.auth_token
            else:
                params['Bugzilla_token'] = self.auth_token

        encoding = 'utf-8'
        return dumps((params,), method, encoding=encoding,
                     allow_none=False).encode(encoding, 'xmlcharrefreplace')

    def parse_response(self, response):
        """Send request object and perform checks on the response."""
        data = self._parse_xml(IterContent(response))[0]
        if not data.get('faults', None):
            return data
        else:
            error = data.get('faults')[0]
            if error.get('faultCode') == 102:
                raise AuthError('access denied')
            raise RequestError(msg=error.get('faultString'), code=error.get('faultCode'))

    @staticmethod
    def _parse_xml(response):
        """Parse XML data from response."""
        stream = response

        p, u = getparser(use_datetime=True)

        while 1:
            data = stream.read(64*1024)
            if not data:
                break
            try:
                p.feed(data)
            except Exception:
                raise RequestError('error decoding response, XML-RPC interface likely disabled on server')

        if stream is not response:
            stream.close()
        p.close()

        return u.close()


class IterContent(object):

    def __init__(self, file, size=64*1024):
        self.initial = True
        self.chunks = file.iter_content(chunk_size=size)

    def read(self, size=64*1024):
        try:
            return next(self.chunks)
        except StopIteration:
            return

class BugzillaAttachmentXml(BugzillaAttachment):

    @decompress
    def read(self):
        return self.data.data.decode()
