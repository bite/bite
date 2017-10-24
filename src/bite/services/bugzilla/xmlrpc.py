from xmlrpc.client import dumps, getparser

from bite.objects import decompress
from bite.exceptions import RequestError, AuthError
from bite.services.bugzilla import Bugzilla, BugzillaAttachment

from requests import Request


class BugzillaXmlrpc(Bugzilla):
    """Support Bugzilla's deprecated XML-RPC interface."""

    def __init__(self, **kw):
        self.endpoint = '/xmlrpc.cgi'
        self.headers = {'Content-Type': 'text/xml'}
        super().__init__(**kw)
        self.attachment = BugzillaAttachmentXml

    def create_request(self, method, params=None):
        """Construct an XML-RPC request."""
        encoding = 'utf-8'
        allow_none = False
        params = (super().inject_auth(params),)

        xml_data = dumps(params, method, encoding=encoding,
                         allow_none=allow_none).encode(encoding, 'xmlcharrefreplace')
        req = Request(method='POST', url=self._base, data=xml_data, headers=self.headers)
        return req.prepare()

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
