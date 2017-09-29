from urllib.parse import urlparse, urlunparse
from xmlrpc.client import dumps, getparser

from bite.objects import decompress
from bite.exceptions import RequestError, AuthError
from bite.services.bugzilla import Bugzilla, BugzillaAttachment

from requests import Request


class BugzillaXmlrpc(Bugzilla):
    def __init__(self, **kw):
        url = urlparse(kw['base'])
        path = url.path.rpartition('/')[0]
        url = (url.scheme, url.netloc, path + '/xmlrpc.cgi', None, None, None)
        self._base = urlunparse(url)

        self.headers = {'Content-Type': 'text/xml'}

        super().__init__(**kw)
        self.attachment = BugzillaAttachmentXml

    def create_request(self, method, params=None):
        """Construct and return a tuple containing the XMLRPC method and params to send."""
        encoding = 'utf-8'
        allow_none = False
        params = (params,)

        xml_data = dumps(params, method, encoding=encoding,
                         allow_none=allow_none).encode(encoding, 'xmlcharrefreplace')
        req = Request(method='POST', url=self._base, data=xml_data,
                      cookies=self.auth_token, headers=self.headers)
        return req.prepare()

    def send(self, request):
        """Send request object and perform checks on the response."""
        r = super().send(request)

        if r.ok:
            return self.parse_response(IterContent(r))[0]
        else:
            if r.status_code == 410:
                raise AuthError(r.reason)
            elif r.status_code == 411 and self.uri.startswith('http:'):
                # Bugzilla strangely returns an error under http but works fine under https
                raise RequestError('Received error reply, try using an https:// url instead')
            else:
                raise RequestError(r.reason)

    @staticmethod
    def parse_response(response):
        # read response data from httpresponse, and parse it
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
