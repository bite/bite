from .. import args


class RedmineOpts(args.ServiceOpts):
    """Redmine options."""


class RedmineElasticOpts(RedmineOpts):
    """Redmine with elasticsearch options."""


class RedmineJsonOpts(RedmineOpts):
    __doc__ = RedmineOpts.__doc__
    _service = 'redmine-json'


class RedmineElasticJsonOpts(RedmineElasticOpts):
    __doc__ = RedmineElasticOpts.__doc__
    _service = 'redmine-elastic-json'


class RedmineXmlOpts(RedmineOpts):
    __doc__ = RedmineOpts.__doc__
    _service = 'redmine-xml'


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


@args.subcmd(RedmineOpts)
class Search(_BaseSearch):
    pass


@args.subcmd(RedmineElasticOpts)
class Search(_BaseSearch):

    def add_args(self):
        super().add_args()
        attr = self.parser.add_argument_group('Attribute related')
        attr.add_argument(
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
