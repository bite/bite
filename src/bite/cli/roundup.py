from . import Cli
from .. import const

class Roundup(Cli):
    """CLI for Roundup service."""

    service_name = 'roundup'

    def print_search(self, issues, **kw):
        count = 0
        for issue in issues:
            print(issue)
            count += 1
        return count

    def _print_item(self, issues, **kw):
        for issue in issues:
            print('=' * const.COLUMNS)
            print(issue)
