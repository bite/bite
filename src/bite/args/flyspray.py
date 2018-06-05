from .. import args


class FlysprayScraperOpts(args.ServiceOpts):
    """Flyspray web scraper"""

    _service = 'flyspray-scraper'


class Search(args.Search, FlysprayScraperOpts):

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
        time.add_argument(
            '--due', type='time interval', metavar='TIME_INTERVAL',
            help=f'{self.service.item.type}s due within a specified time interval')

        attr = self.parser.add_argument_group('Attribute related')
        attr.add_argument(
            '-s', '--status', type='str_list', action='parse_stdin',
            help='restrict by status (one or more)',
            docs="""
                Restrict issues returned by their status.

                Multiple statuses can be entered as comma-separated values in
                which case results match any of the given values.
            """)
