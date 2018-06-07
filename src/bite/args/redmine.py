from .. import args


class RedmineOpts(args.ServiceOpts):
    """Redmine"""

    _service = 'redmine'


class RedmineElasticOpts(RedmineOpts):
    """Redmine with elasticsearch"""

    _service = 'redmine-elastic'


class _BaseSearch(args.PagedSearch):

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

        self.time = self.parser.add_argument_group('Time related')
        self.time.add_argument(
            '-c', '--created', type='time interval', metavar='TIME_INTERVAL',
            help='bugs created within a specified time interval')
        self.time.add_argument(
            '-m', '--modified', type='time interval', metavar='TIME_INTERVAL',
            help='bugs modified within a specified time interval')
        self.time.add_argument(
            '--closed', type='time interval', metavar='TIME_INTERVAL',
            help='bugs closed within a specified time interval')

        self.attr = self.parser.add_argument_group('Attribute related')


class _RegularSearch(_BaseSearch, RedmineOpts):

    def add_args(self):
        super().add_args()
        # TODO: requires cached service categories
        # self.attr.add_argument(
            # '--category',
            # help='restrict by category',
            # docs="""
                # Restrict issues returned by their category.
            # """)
        self.attr.add_argument(
            '-s', '--status',
            help='restrict by status',
            docs="""
                Restrict issues returned by their status.
            """)


class _ElasticSearch(_BaseSearch, RedmineElasticOpts):

    def add_args(self):
        super().add_args()
        self.attr.add_argument(
            '--category', type='str_list', action='parse_stdin',
            help='restrict by category (one or more)',
            docs="""
                Restrict issues returned by their category.

                Multiple categories can be entered as comma-separated values in
                which case results match any of the given values.
            """)
        self.attr.add_argument(
            '-s', '--status', type='str_list', action='parse_stdin',
            help='restrict by status (one or more)',
            docs="""
                Restrict issues returned by their status.

                Multiple statuses can be entered as comma-separated values in
                which case results match any of the given values.
            """)


class Get(args.Get, RedmineOpts):
    pass


class Comments(args.Comments, RedmineOpts):
    pass
