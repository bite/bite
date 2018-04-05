from . import Bugzilla


class BugzillaXmlrpc(Bugzilla):
    """CLI for Bugzilla XML-RPC interface."""

    _service = 'bugzilla-xmlrpc'
