from .. import args


class JiraOpts(args.ServiceOpts):
    """Jira options."""

    _service = 'jira'


@args.subcmd(JiraOpts)
class Search(args.PagedSearch):

    def add_args(self):
        super().add_args()

        self.time = self.parser.add_argument_group('Time related')
        self.time.add_argument(
            '-c', '--created', type='time interval', metavar='TIME_INTERVAL',
            help=f'{self.service.item.type}s created within a specified time interval')
        self.time.add_argument(
            '-m', '--modified', type='time interval', metavar='TIME_INTERVAL',
            help=f'{self.service.item.type}s modified within a specified time interval')

        self.attr = self.parser.add_argument_group('Attribute related')
        self.attr.add_argument(
            '--votes',
            help=f'{self.service.item.type}s with the specified number of votes or greater')
