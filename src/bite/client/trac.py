from . import Cli


class Trac(Cli):
    """CLI for Trac service."""

    _service = 'trac'

    def version(self, **kw):
        version = self.service.version()
        print(f'Trac version: {version}')
