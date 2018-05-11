from .bugzilla import date
from .. import args


class RoundupOpts(args.ServiceOpts):
    """Roundup options."""

    _service = 'roundup'


@args.subcmd(RoundupOpts)
class Search(args.Search):

    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        self.opts.add_argument(
            '--sort', action='csv', metavar='TERM',
            help='sorting order for search query',
            docs="""
                Requested sorting order for the given search query.

                Providing multiple sorting terms will give a data response
                sorted by the first term, then the second, and so on.

                Sorting in descending order can be done by prefixing a given
                sorting term with '-'; otherwise, sorting is done in an
                ascending fashion by default.
            """)
        time = self.parser.add_argument_group('Time related')
        time.add_argument(
            '-c', '--created', type=date, metavar='TIME',
            help=f'{self.service.item.type}s created at this time or later')
        time.add_argument(
            '-m', '--modified', type=date, metavar='TIME',
            help=f'{self.service.item.type}s modified at this time or later')


@args.subcmd(RoundupOpts)
class Get(args.Get):
    pass


@args.subcmd(RoundupOpts)
class Attachments(args.Attachments):
    pass


@args.subcmd(RoundupOpts)
class Schema(args.Subcmd):

    def __init__(self, *args, **kw):
        super().__init__(*args, desc='get Roundup db schema', **kw)
