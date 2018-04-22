from .bugzilla import date
from .. import args
from ..argparser import parse_stdin, string_list


class LaunchpadOpts(args.ServiceOpts):

    _service = 'launchpad'


@args.subcmd(LaunchpadOpts)
class Search(args.PagedSearch):
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
            '-i', '--importance', action='csv',
            help='restrict by importance (one or more)')
        attr.add_argument(
            '-M', '--milestone',
            help='restrict by milestone')
        attr.add_argument(
            '-s', '--status', type=string_list,
            action=parse_stdin,
            help='restrict by status (one or more)')
        attr.add_argument(
            '--omit-duplicates', action='store_true',
            help='hide bugs marked as duplicates (shown by default)')
        attr.add_argument(
            '--has-patch', action='store_true',
            help='restrict by bugs that have patches')
        attr.add_argument(
            '--has-cve', action='store_true',
            help='restrict by bugs that have CVEs')
        attr.add_argument(
            '--tags', action='csv',
            help='search by bug tags',
            docs="""
                Search for bugs by tags.

                Multiple tags can be provided using a comma-separated or
                space-separated list. A string of comma-separated tags is
                searched for any matches while a string of space-separated tags
                is searched for all matches. Note that the string-separated
                list must be surrounded with quotes.

                In order to exclude tags use the '-' prefix, e.g. searching for
                bugs with tags matching '-test' would return bugs that don't
                have the 'test' tag.

                To search for tag existence, use the '*' argument to find all
                bugs with one or more tags. Conversely, use the '-*' argument
                to find all bugs with no tags.
            """)


@args.subcmd(LaunchpadOpts)
class Get(args.Get):
    pass
