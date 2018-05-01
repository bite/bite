from snakeoil.demandload import demandload

from . import Cli

demandload('bite:const')


class Roundup(Cli):
    """CLI for Roundup service."""

    _service = 'roundup'

    def schema(self, **kw):
        schema = self.service.schema()
        for k, v in sorted(schema.items()):
            print(k)
            for x in sorted(v):
                print(f'  {x[0]}: {x[1]}')

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

            if issue.attachments:
                attachments = [str(a) for a in issue.attachments]
                if attachments:
                    if str(issue):
                        print()
                    print('\n'.join(attachments))

            if issue.comments and (str(issue) or issue.attachments):
                print()
            self._print_lines((str(x) for x in issue.comments))
