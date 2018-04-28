from . import Cli


class Trac(Cli):
    """CLI for Trac service."""


class TracJsonrpc(Trac):

    _service = 'trac-jsonrpc'


class TracXmlrpc(Trac):

    _service = 'trac-xmlrpc'
