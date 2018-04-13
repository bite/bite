"""Support Bugzilla's deprecated XML-RPC interface.

API docs: https://www.bugzilla.org/docs/4.4/en/html/api/Bugzilla/WebService/Server/XMLRPC.html
"""

from . import BugzillaAttachment
from ._rpc import BugzillaRpc
from .._xmlrpc import Xmlrpc
from ...objects import decompress


class Bugzilla4_4Xmlrpc(BugzillaRpc, Xmlrpc):
    """Service for Bugzilla 4.4 XML-RPC interface."""

    _service = 'bugzilla4.4-xmlrpc'

    def __init__(self, **kw):
        super().__init__(endpoint='/xmlrpc.cgi', **kw)
        self.attachment = BugzillaAttachmentXml


class Bugzilla5_0Xmlrpc(Bugzilla4_4Xmlrpc):
    """Service for Bugzilla 5.0 XML-RPC interface."""

    _service = 'bugzilla5.0-xmlrpc'


class BugzillaXmlrpc(Bugzilla4_4Xmlrpc):
    """Service for Bugzilla latest XML-RPC interface."""

    _service = 'bugzilla-xmlrpc'


class BugzillaAttachmentXml(BugzillaAttachment):

    @decompress
    def read(self):
        return self.data.data
