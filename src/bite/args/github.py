from .. import args


class GithubRestOpts(args.ServiceOpts):
    """Github API v3"""

    _service = 'github-rest'


class _BaseSearch(args.PagedSearch):

    def add_args(self, item=None):
        super().add_args()
        item = item if item is not None else self.service.item.type
        person = self.parser.add_argument_group('Person related')
        person.add_argument(
            '-a', '--assignee', action='csv_negations',
            help=f'user the {item} is assigned to')
        person.add_argument(
            '-r', '--creator', action='csv_negations',
            help=f'user who created the {item}')
        person.add_argument(
            '--mentions', action='csv_negations',
            help=f'user mentioned in the {item}')
        person.add_argument(
            '--commenter', action='csv_negations',
            help=f'user commented on the {item}')

        self.time = self.parser.add_argument_group('Time related')
        self.time.add_argument(
            '-c', '--created', type='time interval', metavar='TIME_INTERVAL',
            help=f'{item}s created within a specified time interval')
        self.time.add_argument(
            '-m', '--modified', type='time interval', metavar='TIME_INTERVAL',
            help=f'{item}s modified within a specified time interval')
        self.time.add_argument(
            '--closed', type='time interval', metavar='TIME_INTERVAL',
            help=f'{item}s closed within a specified time interval')

        self.attr = self.parser.add_argument_group('Attribute related')
        self.attr.add_argument(
            '-M', '--milestone', action='csv_negations',
            help='restrict by milestone')
        self.attr.add_argument(
            '-s', '--status', action='csv',
            help='restrict by status')
        self.attr.add_argument(
            '--label', action='csv_negations',
            help=f'restrict by {item} labels')
        self.attr.add_argument(
            '--comments', type='int range',
            help='restrict by number of comments')


class Search(_BaseSearch, GithubRestOpts):
    """Search for issues."""


class PRs(args.Subcmd, GithubRestOpts):

    _name = 'pr'

    @property
    def description(self):
        return 'operate on pull requests'


class PRSearch(_BaseSearch, GithubRestOpts):
    """Search for pull requests."""

    _name = 'pr search'

    @property
    def description(self):
        return 'search pull requests'

    def add_args(self):
        item = 'pull request'
        super().add_args(item=item)

        self.time.add_argument(
            '--merged', type='time interval', metavar='TIME_INTERVAL',
            help=f'{item}s merged within a specified time interval')

        self.attr.add_argument(
            '--head',
            help='restrict pull requests based on the branch they came from')
        self.attr.add_argument(
            '--base',
            help='restrict pull requests based on the branch they are merging into')
        self.attr.add_argument(
            '--sha',
            help='restrict pull requests containing a specific commit SHA hash',
            docs="""
                Filter pull requests to those containing a commit with the
                specified SHA hash.

                Note that this overrides generic search terms if both are
                specified.
            """)
