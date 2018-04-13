from . import Bugzilla


class Bugzilla4_4Xmlrpc(Bugzilla):

    _service = 'bugzilla4.4-xmlrpc'


class Bugzilla5_0Xmlrpc(Bugzilla):

    _service = 'bugzilla5.0-xmlrpc'


class BugzillaXmlrpc(Bugzilla):
    """CLI for Bugzilla XML-RPC interface."""

    _service = 'bugzilla-xmlrpc'
