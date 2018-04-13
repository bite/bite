from . import Bugzilla


class Bugzilla4_4Jsonrpc(Bugzilla):
    """CLI for Bugzilla 4.4 JSON-RPC interface."""

    _service = 'bugzilla4.4-jsonrpc'


class Bugzilla5_0Jsonrpc(Bugzilla):
    """CLI for Bugzilla 5.0 JSON-RPC interface."""

    _service = 'bugzilla5.0-jsonrpc'


class BugzillaJsonrpc(Bugzilla):
    """CLI for Bugzilla latest JSON-RPC interface."""

    _service = 'bugzilla-jsonrpc'
