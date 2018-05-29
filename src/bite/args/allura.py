from functools import partial

from ..argparser import ParseStdin
from .. import args


class AlluraOpts(args.ServiceOpts):
    """Allura options."""

    _service = 'allura'


@args.subcmd(AlluraOpts)
class Search(args.Search):

    def add_args(self):
        super().add_args()
        # optional args
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
            '-c', '--created', type='date', metavar='TIME',
            help=f'{self.service.item.type}s created at this time or later')
        time.add_argument(
            '-m', '--modified', type='date', metavar='TIME',
            help=f'{self.service.item.type}s modified at this time or later')
        attr = self.parser.add_argument_group('Attribute related')
        attr.add_argument(
            '--id', type='id_list',
            action=partial(ParseStdin, 'ids'),
            help=f'restrict by {self.service.item.type} ID(s)')
        attr.add_argument(
            '-a', '--assignee', type='str_list', action='parse_stdin',
            help=f'person the {self.service.item.type} is assigned to')
        attr.add_argument(
            '-r', '--creator',
            type='str_list', action='parse_stdin',
            help=f'person who created the {self.service.item.type}')


@args.subcmd(AlluraOpts)
class Get(args.Get):

    def add_args(self):
        super().add_args(history=True)


@args.subcmd(AlluraOpts)
class Changes(args.Changes):

    def add_args(self):
        super().add_args()
        # optional args
        self.opts.add_argument(
            '-c', '--created', dest='creation_time',
            metavar='TIME', type='date',
            help='changes made at this time or later')
        self.opts.add_argument(
            '-m', '--match', action='csv',
            help='restrict by matching changed fields')


@args.subcmd(AlluraOpts)
class Comments(args.Comments):
    pass
