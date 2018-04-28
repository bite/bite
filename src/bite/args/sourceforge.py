from .bugzilla import date
from .. import args


class SourceforgeOpts(args.ServiceOpts):

    _service = 'sourceforge'


@args.subcmd(SourceforgeOpts)
class Search(args.Search):

    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        # optional args
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


@args.subcmd(SourceforgeOpts)
class Get(args.Get):

    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        # optional args
        self.opts.add_argument(
            '-H', '--no-history', dest='get_changes', action='store_false',
            help="don't show bug history")


@args.subcmd(SourceforgeOpts)
class Changes(args.Changes):

    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        # optional args
        self.opts.add_argument(
            '-c', '--created', dest='creation_time',
            metavar='TIME', type=date,
            help='changes made at this time or later')
        self.opts.add_argument(
            '-m', '--match', action='csv',
            help='restrict by matching changed fields')


@args.subcmd(SourceforgeOpts)
class Comments(args.Comments):

    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        # optional args
        self.opts.add_argument(
            '-c', '--created', dest='creation_time',
            metavar='TIME', type=date,
            help='comments made at this time or later')
