from . import BugzillaAttachment, BugzillaError
from ._rpc import BugzillaRpc
from .._xmlrpc import Xmlrpc
from ...objects import decompress
from ...exceptions import RequestError, ParsingError


class BugzillaXmlrpc(BugzillaRpc, Xmlrpc):
    """Support Bugzilla's deprecated XML-RPC interface."""

    _service = 'bugzilla-xmlrpc'

    def __init__(self, **kw):
        super().__init__(endpoint='/xmlrpc.cgi', **kw)
        self.attachment = BugzillaAttachmentXml

    def parse_response(self, response):
        """Send request object and perform checks on the response."""
        try:
            data = super().parse_response(response)
        except ParsingError as e:
            # The default expat parser has issues with certain data, e.g.
            # https://bugs.gentoo.org/532044 -- running a get command against
            # that bug returns an invalid token parsing error. This is "fixed"
            # by using lxml for parsing which allows recovering from certain
            # types of broken XML.
            #
            # A better alternative is using the jsonrpc interface if that's available.
            msg = e.msg + ", use the jsonrpc interface if available"
            raise ParsingError(msg=msg, text=e.text)
        except RequestError as e:
            raise BugzillaError(msg=e.msg, code=e.code, text=e.text)

        faults = data.get('faults')
        if not faults:
            return data
        else:
            self.handle_error(code=faults[0]['faultCode'], msg=faults[0]['faultString'])


class BugzillaAttachmentXml(BugzillaAttachment):

    @decompress
    def read(self):
        return self.data.data
