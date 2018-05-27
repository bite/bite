from .. import args


class TracOpts(args.ServiceOpts):
    """Trac options."""


class TracJsonrpcOpts(TracOpts):
    __doc__ = TracOpts.__doc__
    _service = 'trac-jsonrpc'


class TracXmlrpcOpts(TracOpts):
    __doc__ = TracOpts.__doc__
    _service = 'trac-xmlrpc'


@args.subcmd(TracOpts)
class Search(args.Search):

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
            '-c', '--created', type='date', metavar='TIME',
            help=f'{self.service.item.type}s created at this time or later')
        time.add_argument(
            '-m', '--modified', type='date', metavar='TIME',
            help=f'{self.service.item.type}s modified at this time or later')
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


@args.subcmd(TracOpts)
class Get(args.Get):

    def add_args(self):
        super().add_args(history=True)


@args.subcmd(TracOpts)
class Comments(args.Comments):
    pass


@args.subcmd(TracOpts)
class Changes(args.Changes):
    pass


@args.subcmd(TracOpts)
class Version(args.Subcmd):
    """get Trac version"""


class TracScraperOpts(args.ServiceOpts):
    """Trac web scraper options."""
    _service = 'trac-scraper'


@args.subcmd(TracScraperOpts, name='search')
class _ScrapedSearch(Search):
    pass
