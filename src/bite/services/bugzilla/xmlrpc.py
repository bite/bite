from . import Bugzilla, BugzillaAttachment, BugzillaError
from .._xmlrpc import Xmlrpc
from ...objects import decompress
from ...exceptions import AuthError, RequestError


class BugzillaXmlrpc(Bugzilla, Xmlrpc):
    """Support Bugzilla's deprecated XML-RPC interface."""

    def __init__(self, **kw):
        kw['endpoint'] = '/xmlrpc.cgi'
        super().__init__(**kw)
        self.attachment = BugzillaAttachmentXml

    def parse_response(self, response):
        """Send request object and perform checks on the response."""
        try:
            data = super().parse_response(response)
        except RequestError as e:
            raise BugzillaError(msg=e.msg, code=e.code, text=e.text)

        if not data.get('faults', None):
            return data
        else:
            error = data.get('faults')[0]
            if error.get('faultCode') == 102:
                raise AuthError('access denied')
            raise BugzillaError(msg=error.get('faultString'), code=error.get('faultCode'))


class BugzillaAttachmentXml(BugzillaAttachment):

    @decompress
    def read(self):
        return self.data.data.decode()
