from . import Cli


class Trac(Cli):
    """CLI for Trac service."""

    _service = 'trac'

    def login(self, *args, **kw):
        """Try to switch to the JSON-RPC based service before logging in."""
        try:
            self.service = self.service._morph()
        except AttributeError:
            pass
        super().login(*args, **kw)

    def version(self, **kw):
        version = self.service.version()
        print(f'Trac version: {version}')
