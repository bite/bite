from . import Cli


class Trac(Cli):
    """CLI for Trac service."""

    def version(self, **kw):
        version = self.service.version()
        print(f'Trac version: {version}')


class TracScraper(Cli):

    _service = 'trac-scraper'


class TracJsonrpc(Trac):

    _service = 'trac-jsonrpc'


class TracXmlrpc(Trac):

    _service = 'trac-xmlrpc'
