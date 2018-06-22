from .. import args


class GithubRestOpts(args.ServiceOpts):
    """Github REST API v3 options."""

    _service = 'github-rest'


class Search(args.PagedSearch, GithubRestOpts):

    def add_args(self):
        super().add_args()
        attr = self.parser.add_argument_group('Attribute related')
        attr.add_argument(
            '--label', action='csv_negations',
            help=f'restrict by {self.service.item.type} labels')
