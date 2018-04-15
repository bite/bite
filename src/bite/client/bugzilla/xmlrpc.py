from . import Bugzilla


class Bugzilla4_4Xmlrpc(Bugzilla):
    """CLI for Bugzilla 4.4 XML-RPC interface."""

    _service = 'bugzilla4.4-xmlrpc'


class Bugzilla5_0Xmlrpc(Bugzilla):
    """CLI for Bugzilla 5.0 XML-RPC interface."""

    _service = 'bugzilla5.0-xmlrpc'


class Bugzilla5_2Xmlrpc(Bugzilla):
    """CLI for Bugzilla 5.2 XML-RPC interface."""

    _service = 'bugzilla5.2-xmlrpc'
