from snakeoil.demandload import demandload
from snakeoil.strings import pluralism

from . import Cli, dry_run, login_retry

demandload('bite:const')


class Github(Cli):
    """CLI for Github service."""

    _service = 'github'

    @dry_run
    @login_retry
    def pr_search(self, **kw):
        """Search for pull requests on Github."""
        request = self.service.PRSearchRequest(params=kw)

        self.log(f'Searching for pull requests with the following options:')
        self.log_t(request.options, prefix='   - ')

        data = request.send()

        lines = self._render_search(data, **kw)
        count = 0
        for line in lines:
            count += 1
            print(line[:const.COLUMNS])
        self.log(f"{count} pull request{pluralism(count)} found.")
