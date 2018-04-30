from .bugzilla import date
from .. import args


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
        time = self.parser.add_argument_group('Time related')
        time.add_argument(
            '-c', '--created', type=date, metavar='TIME',
            help=f'tickets created at this time or later')
        time.add_argument(
            '-m', '--modified', type=date, metavar='TIME',
            help=f'tickets modified at this time or later')
