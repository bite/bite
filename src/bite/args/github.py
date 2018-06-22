from .. import args


class GithubRestOpts(args.ServiceOpts):
    """Github REST API v3 options."""

    _service = 'github-rest'


class Search(args.PagedSearch, GithubRestOpts):

    def add_args(self):
        super().add_args()
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
            '--label', action='csv_negations',
            help=f'restrict by {self.service.item.type} labels')
        attr.add_argument(
            '-s', '--status',
            help='restrict by status')
        attr.add_argument(
            '--comments', type='int range',
            help='restrict by number of comments')
