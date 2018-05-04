from .bugzilla import date
from .. import args
from ..argparser import parse_stdin, string_list


class TracOpts(args.ServiceOpts):
    pass


class TracJsonrpcOpts(TracOpts):

    _service = 'trac-jsonrpc'


class TracXmlrpcOpts(TracOpts):

    _service = 'trac-xmlrpc'


@args.subcmd(TracOpts)
class Search(args.Search):

    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        self.opts.add_argument(
            '--sort', dest='order', metavar='TERM',
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
            '-c', '--created', type=date, metavar='TIME',
            help=f'{self.service.item.type}s created at this time or later')
        time.add_argument(
            '-m', '--modified', type=date, metavar='TIME',
            help=f'{self.service.item.type}s modified at this time or later')
        attr = self.parser.add_argument_group('Attribute related')
        attr.add_argument(
            '-a', '--assigned-to', dest='owner', type=string_list, action=parse_stdin,
            help=f'person the {self.service.item.type} is assigned to')
        attr.add_argument(
            '-r', '--creator', dest='reporter',
            type=string_list, action=parse_stdin,
            help=f'person who created the {self.service.item.type}')


@args.subcmd(TracOpts)
class Version(args.Subcmd):

    def __init__(self, *args, **kw):
        super().__init__(*args, desc='get Trac version', **kw)
