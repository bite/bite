from functools import partial

from .bugzilla import date
from ..argparser import parse_stdin, id_list, ids, string_list
from .. import args


class SourceforgeOpts(args.ServiceOpts):

    _service = 'sourceforge'


@args.subcmd(SourceforgeOpts)
class Search(args.Search):

    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
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
            '-c', '--created', type=date,
            dest='created_date', metavar='TIME',
            help=f'{self.service.item.type}s created at this time or later')
        time.add_argument(
            '-m', '--modified', type=date,
            dest='mod_date', metavar='TIME',
            help=f'{self.service.item.type}s modified at this time or later')
        attr = self.parser.add_argument_group('Attribute related')
        attr.add_argument(
            '--id', type=id_list,
            action=partial(parse_stdin, ids),
            help=f'restrict by {self.service.item.type} ID(s)')
        attr.add_argument(
            '-a', '--assigned-to', type=string_list, action=parse_stdin,
            help=f'person the {self.service.item.type} is assigned to')
        attr.add_argument(
            '-r', '--creator', dest='reported_by',
            type=string_list, action=parse_stdin,
            help=f'person who created the {self.service.item.type}')


@args.subcmd(SourceforgeOpts)
class Get(args.Get):

    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        # optional args
        self.opts.add_argument(
            '-H', '--no-history', dest='get_changes', action='store_false',
            help=f"don't show {self.service.item.type} history")


@args.subcmd(SourceforgeOpts)
class Changes(args.Changes):

    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        # optional args
        self.opts.add_argument(
            '-c', '--created', dest='creation_time',
            metavar='TIME', type=date,
            help='changes made at this time or later')
        self.opts.add_argument(
            '-m', '--match', action='csv',
            help='restrict by matching changed fields')


@args.subcmd(SourceforgeOpts)
class Comments(args.Comments):

    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        # optional args
        self.opts.add_argument(
            '-c', '--created', dest='creation_time',
            metavar='TIME', type=date,
            help='comments made at this time or later')
