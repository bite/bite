from .. import args


class RoundupOpts(args.ServiceOpts):
    """Roundup"""

    _service = 'roundup'


class Search(args.Search, RoundupOpts):

    def add_args(self):
        super().add_args()
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

        time = self.parser.add_argument_group('Time related')
        time.add_argument(
            '-c', '--created', type='time interval', metavar='TIME_INTERVAL',
            help=f'{self.service.item.type}s created within a specified time interval')
        time.add_argument(
            '-m', '--modified', type='time interval', metavar='TIME_INTERVAL',
            help=f'{self.service.item.type}s modified within a specified time interval')


class Get(args.Get, RoundupOpts):
    pass


class Attachments(args.Attachments, RoundupOpts):
    pass


class Comments(args.Comments, RoundupOpts):
    pass


class Schema(args.Subcmd, RoundupOpts):
    """get Roundup db schema"""

    _name = 'schema'
