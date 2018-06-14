from . import Cli


class Jira(Cli):
    """CLI for Jira service."""

    _service = 'jira'

    def version(self, **kw):
        version = self.service.version()
        print(f'Jira version: {version}')
