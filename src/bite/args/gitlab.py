from .. import args


class GitlabOpts(args.ServiceOpts):
    """Gitlab options."""

    _service = 'gitlab'


class Search(args.PagedSearch, GitlabOpts):

    def add_args(self):
        super().add_args()
        time = self.parser.add_argument_group('Time related')
        time.add_argument(
            '-c', '--created', type='time interval', metavar='TIME_INTERVAL',
            help=f'{self.service.item.type}s created within a specified time interval')
        time.add_argument(
            '-m', '--modified', type='time interval', metavar='TIME_INTERVAL',
            help=f'{self.service.item.type}s modified within a specified time interval')
