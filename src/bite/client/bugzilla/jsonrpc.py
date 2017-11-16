from . import Bugzilla

class BugzillaJsonrpc(Bugzilla):
    """CLI for Bugzilla JSON-RPC interface."""

    _service = 'bugzilla-jsonrpc'
