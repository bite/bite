"""Support Bugzilla's deprecated XML-RPC interface.

API docs: https://www.bugzilla.org/docs/4.4/en/html/api/Bugzilla/WebService/Server/XMLRPC.html
"""

from . import BugzillaAttachment
from ._rpc import Bugzilla4_4Rpc, Bugzilla5_0Rpc
from .._xmlrpc import Xmlrpc
from ...objects import decompress


class _BugzillaXmlrpcBase(Xmlrpc):
    """Base service class for Bugzilla XML-RPC interface."""

    def __init__(self, **kw):
        super().__init__(endpoint='/xmlrpc.cgi', **kw)
        self.attachment = BugzillaAttachmentXml


class Bugzilla4_4Xmlrpc(_BugzillaXmlrpcBase, Bugzilla4_4Rpc):
    """Service for Bugzilla 4.4 XML-RPC interface."""

    _service = 'bugzilla4.4-xmlrpc'


class Bugzilla5_0Xmlrpc(_BugzillaXmlrpcBase, Bugzilla5_0Rpc):
    """Service for Bugzilla 5.0 XML-RPC interface."""

    _service = 'bugzilla5.0-xmlrpc'


class BugzillaXmlrpc(_BugzillaXmlrpcBase, Bugzilla5_0Rpc):
    """Service for Bugzilla latest XML-RPC interface."""

    _service = 'bugzilla-xmlrpc'


class BugzillaAttachmentXml(BugzillaAttachment):

    @decompress
    def read(self):
        return self.data.data
