"""Support Bugzilla's deprecated XML-RPC interface.

API docs: https://www.bugzilla.org/docs/4.4/en/html/api/Bugzilla/WebService/Server/XMLRPC.html
"""

from . import BugzillaAttachment
from ._rpc import BugzillaRpc
from .._xmlrpc import Xmlrpc
from ...objects import decompress


class BugzillaXmlrpc(BugzillaRpc, Xmlrpc):
    """Service supporting Bugzilla's deprecated XML-RPC interface."""

    _service = 'bugzilla-xmlrpc'

    def __init__(self, **kw):
        super().__init__(endpoint='/xmlrpc.cgi', **kw)
        self.attachment = BugzillaAttachmentXml


class BugzillaAttachmentXml(BugzillaAttachment):

    @decompress
    def read(self):
        return self.data.data
