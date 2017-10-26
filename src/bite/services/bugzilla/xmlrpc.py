from . import Bugzilla, BugzillaAttachment
from .._xmlrpc import Xmlrpc
from ...objects import decompress
from ...exceptions import RequestError, AuthError


class BugzillaXmlrpc(Bugzilla, Xmlrpc):
    """Support Bugzilla's deprecated XML-RPC interface."""

    def __init__(self, **kw):
        kw['endpoint'] = '/xmlrpc.cgi'
        super().__init__(**kw)
        self.attachment = BugzillaAttachmentXml

    def parse_response(self, response):
        """Send request object and perform checks on the response."""
        data = super().parse_response(response)
        if not data.get('faults', None):
            return data
        else:
            error = data.get('faults')[0]
            if error.get('faultCode') == 102:
                raise AuthError('access denied')
            raise RequestError(msg=error.get('faultString'), code=error.get('faultCode'))


class BugzillaAttachmentXml(BugzillaAttachment):

    @decompress
    def read(self):
        return self.data.data.decode()
