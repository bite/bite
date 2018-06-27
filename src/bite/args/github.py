from .. import args


class GithubRestOpts(args.ServiceOpts):
    """Github REST API v3 options."""

    _service = 'github-rest'


class Search(args.PagedSearch, GithubRestOpts):

    def add_args(self):
        super().add_args()
        person = self.parser.add_argument_group('Person related')
        person.add_argument(
            '-a', '--assignee', action='csv_negations',
            help=f'user the {self.service.item.type} is assigned to')
        person.add_argument(
            '-r', '--creator', action='csv_negations',
            help=f'user who created the {self.service.item.type}')
        person.add_argument(
            '--mentions', action='csv_negations',
            help=f'user mentioned in the {self.service.item.type}')
        person.add_argument(
            '--commenter', action='csv_negations',
            help=f'user commented on the {self.service.item.type}')

        time = self.parser.add_argument_group('Time related')
        time.add_argument(
            '-c', '--created', type='time interval', metavar='TIME_INTERVAL',
            help=f'{self.service.item.type}s created within a specified time interval')
        time.add_argument(
            '-m', '--modified', type='time interval', metavar='TIME_INTERVAL',
            help=f'{self.service.item.type}s modified within a specified time interval')
        time.add_argument(
            '--closed', type='time interval', metavar='TIME_INTERVAL',
            help=f'{self.service.item.type}s closed within a specified time interval')

        attr = self.parser.add_argument_group('Attribute related')
        attr.add_argument(
            '-M', '--milestone', action='csv_negations',
            help='restrict by milestone')
        attr.add_argument(
            '-s', '--status',
            help='restrict by status')
        attr.add_argument(
            '--label', action='csv_negations',
            help=f'restrict by {self.service.item.type} labels')
        attr.add_argument(
            '--comments', type='int range',
            help='restrict by number of comments')
