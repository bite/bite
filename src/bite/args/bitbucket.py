from functools import partial

from .. import args
from ..argparser import ParseStdin


class BitbucketOpts(args.ServiceOpts):
    """Bitbucket options."""

    _service = 'bitbucket'


@args.subcmd(BitbucketOpts)
class Search(args.Search):

    def add_args(self):
        super().add_args()
        # optional args
        self.opts.add_argument(
            '--sort', metavar='TERM',
            help='sorting order for search query',
            docs="""
                Requested sorting order for the given search query.

                Only one field can be sorted on for a query, compound fields
                sorting is not supported.

                Sorting in descending order can be done by prefixing a given
                sorting term with '-'; otherwise, sorting is done in an
                ascending fashion by default.
            """)
        time = self.parser.add_argument_group('Time related')
        time.add_argument(
            '-c', '--created', type='date', metavar='TIME',
            help='issues created at this time or later')
        time.add_argument(
            '-m', '--modified', type='date', metavar='TIME',
            help='issues modified at this time or later')
        attr = self.parser.add_argument_group('Attribute related')
        attr.add_argument(
            '--id', type='id_list', action=partial(ParseStdin, 'ids'),
            help='restrict by issue ID(s)')
        attr.add_argument(
            '-p', '--priority', type='str_list', action='parse_stdin',
            help='restrict by priority (one or more)',
            docs="""
                Restrict issues returned by their priority.

                Multiple priorities can be entered as comma-separated values in
                which case results can match any of the given values.
            """)
        attr.add_argument(
            '-s', '--status', type='str_list', action='parse_stdin',
            help='restrict by status (one or more)',
            docs="""
                Restrict issues returned by their status.

                Multiple statuses can be entered as comma-separated values in
                which case results can match any of the given values.
            """)
        attr.add_argument(
            '--type', type='str_list', action='parse_stdin',
            help='restrict by type (one or more)',
            docs="""
                Restrict issues returned by their type.

                Multiple types can be entered as comma-separated values in
                which case results can match any of the given values.
            """)
        attr.add_argument(
            '--votes',
            help='restrict by number of votes or greater')
        attr.add_argument(
            '--watchers',
            help='restrict by number of watchers or greater')


@args.subcmd(BitbucketOpts)
class Get(args.Get):

    def add_args(self):
        super().add_args(history=True)


@args.subcmd(BitbucketOpts)
class Attachments(args.Attachments):

    def add_args(self):
        super().add_args(id_map='id_str_maps', item_id=False)


@args.subcmd(BitbucketOpts)
class Comments(args.Comments):
    pass


@args.subcmd(BitbucketOpts)
class Changes(args.Changes):
    pass
