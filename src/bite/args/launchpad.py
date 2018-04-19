from .bugzilla import date
from .. import args


class LaunchpadOpts(args.ServiceOpts):

    _service = 'launchpad'


@args.subcmd(LaunchpadOpts)
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
        person = self.parser.add_argument_group('Person related')
        person.add_argument(
            '-a', '--assigned-to', dest='owner',
            help='search by bug owner')
        person.add_argument(
            '-r', '--creator', dest='bug_reporter',
            help='search by person who created the bug')
        person.add_argument(
            '--commenter', dest='bug_commenter',
            help='search by commenter in the bug')
        person.add_argument(
            '--cc', dest='bug_subscriber',
            help='search by bug subscriber')
        time = self.parser.add_argument_group('Time related')
        time.add_argument(
            '-c', '--created', type=date,
            dest='created_since', metavar='TIME',
            help='bugs created at this time or later')
        time.add_argument(
            '-m', '--modified', type=date,
            dest='modified_since', metavar='TIME',
            help='bugs modified at this time or later')
        attr = self.parser.add_argument_group('Attribute related')
        attr.add_argument(
            '--has-patch', action='store_true',
            help='restrict by bugs that have patches')
        attr.add_argument(
            '--has-cve', action='store_true',
            help='restrict by bugs that have CVEs')
