from .. import args


class TracOpts(args.ServiceOpts):
    """Trac options."""

    _service = 'trac'


class Search(args.Search, TracOpts):

    def add_args(self):
        super().add_args()
        self.opts.add_argument(
            '--sort', metavar='TERM',
            help='sorting order for search query',
            docs="""
                Requested sorting order for the given search query.

                Sorting in descending order can be done by prefixing a given
                sorting term with '-'; otherwise, sorting is done in an
                ascending fashion by default.

                Note that sorting by multiple terms is not supported.
            """)
        time = self.parser.add_argument_group('Time related')
        time.add_argument(
            '-c', '--created', type='time interval', metavar='TIME_INTERVAL',
            help=f'{self.service.item.type}s created within a specified time interval')
        time.add_argument(
            '-m', '--modified', type='time interval', metavar='TIME_INTERVAL',
            help=f'{self.service.item.type}s modified within a specified time interval')
        attr = self.parser.add_argument_group('Attribute related')
        attr.add_argument(
            '-a', '--assigned-to', dest='owner', type='str_list', action='parse_stdin',
            help=f'person the {self.service.item.type} is assigned to')
        attr.add_argument(
            '-r', '--creator', dest='reporter',
            type='str_list', action='parse_stdin',
            help=f'person who created the {self.service.item.type}')
        attr.add_argument(
            '-s', '--status', type='str_list', action='parse_stdin',
            help='restrict by status (one or more)',
            docs="""
                Restrict issues returned by their status.

                Multiple statuses can be entered as comma-separated values in
                which case results match any of the given values.
            """)


class Get(args.Get, TracOpts):

    def add_args(self):
        super().add_args(history=True)


class Comments(args.Comments, TracOpts):
    pass


class Changes(args.Changes, TracOpts):
    pass


class Version(args.Subcmd, TracOpts):
    """get Trac version"""

    _name = 'version'


class TracScraperOpts(args.ServiceOpts):
    """Trac web scraper options."""

    _service = 'trac-scraper'


class _ScrapedSearch(Search, TracScraperOpts):
    pass
