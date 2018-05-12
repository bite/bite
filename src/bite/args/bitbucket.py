from .bugzilla import date
from .. import args
from ..argparser import parse_stdin, string_list


class BitbucketOpts(args.ServiceOpts):
    """Bitbucket options."""

    _service = 'bitbucket'


@args.subcmd(BitbucketOpts)
class Search(args.Search):

    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        # optional args
        self.opts.add_argument(
            '--sort', metavar='TERM',
            help='sorting order for search query',
            docs="""
                Requested sorting order for the given search query.

                Only one field can be sorted on for a query, compound fields
                sorting is not supported.

                Sorting in descending order can be done by prefixing a given
                sorting term with '-'; otherwise, sorting is done in an
                ascending fashion by default.
            """)
        time = self.parser.add_argument_group('Time related')
        time.add_argument(
            '-c', '--created', type=date, metavar='TIME',
            help='issues created at this time or later')
        time.add_argument(
            '-m', '--modified', type=date, metavar='TIME',
            help='issues modified at this time or later')
        attr = self.parser.add_argument_group('Attribute related')
        attr.add_argument(
            '-s', '--status', type=string_list, action=parse_stdin,
            help='restrict by status (one or more)',
            docs="""
                Restrict issues returned by their status.

                Multiple statuses can be entered as comma-separated values in
                which case results can match any of the given values.
            """)
        attr.add_argument(
            '--votes',
            help='restrict by number of votes or greater')
        attr.add_argument(
            '--watchers',
            help='restrict by number of watchers or greater')


@args.subcmd(BitbucketOpts)
class Get(args.Get):

    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        # optional args
        self.opts.add_argument(
            '-H', '--no-history', dest='get_changes', action='store_false',
            help="don't show bug history")
