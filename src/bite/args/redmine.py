from .. import args


class RedmineOpts(args.ServiceOpts):
    """Redmine options."""


class RedmineElasticOpts(RedmineOpts):
    """Redmine with elasticsearch options."""


class RedmineJsonOpts(RedmineOpts):
    __doc__ = RedmineOpts.__doc__
    _service = 'redmine-json'


class RedmineXmlOpts(RedmineOpts):
    __doc__ = RedmineOpts.__doc__
    _service = 'redmine-xml'


class Redmine3_2JsonOpts(RedmineOpts):
    __doc__ = RedmineOpts.__doc__
    _service = 'redmine3.2-json'


class Redmine3_2XmlOpts(RedmineOpts):
    __doc__ = RedmineOpts.__doc__
    _service = 'redmine3.2-xml'


class RedmineElasticJsonOpts(RedmineElasticOpts):
    __doc__ = RedmineElasticOpts.__doc__
    _service = 'redmine-elastic-json'


class RedmineElasticXmlOpts(RedmineElasticOpts):
    __doc__ = RedmineElasticOpts.__doc__
    _service = 'redmine-elastic-xml'


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


@args.subcmd(RedmineOpts, name='search')
class _RegularSearch(_BaseSearch):

    def add_args(self):
        super().add_args()
        self.attr.add_argument(
            '-s', '--status',
            help='restrict by status',
            docs="""
                Restrict issues returned by their status.
            """)


@args.subcmd(RedmineElasticOpts, name='search')
class _ElasticSearch(_BaseSearch):

    def add_args(self):
        super().add_args()
        self.attr.add_argument(
            '-s', '--status', type='str_list', action='parse_stdin',
            help='restrict by status (one or more)',
            docs="""
                Restrict issues returned by their status.

                Multiple statuses can be entered as comma-separated values in
                which case results can match any of the given values.
            """)


@args.subcmd(RedmineOpts)
class Get(args.Get):
    pass


@args.subcmd(RedmineOpts)
class Comments(args.Comments):
    pass
