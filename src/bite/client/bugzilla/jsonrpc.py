from . import Bugzilla, Bugzilla5_0


class Bugzilla4_4Jsonrpc(Bugzilla):
    """CLI for Bugzilla 4.4 JSON-RPC interface."""

    _service = 'bugzilla4.4-jsonrpc'


class Bugzilla5_0Jsonrpc(Bugzilla5_0):
    """CLI for Bugzilla 5.0 JSON-RPC interface."""

    _service = 'bugzilla5.0-jsonrpc'


class Bugzilla5_2Jsonrpc(Bugzilla5_0):
    """CLI for Bugzilla 5.2 JSON-RPC interface."""

    _service = 'bugzilla5.2-jsonrpc'
