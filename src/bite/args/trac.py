from .. import args


class TracOpts(args.ServiceOpts):
    pass


class TracJsonrpcOpts(TracOpts):

    _service = 'trac-jsonrpc'


class TracXmlrpcOpts(TracOpts):

    _service = 'trac-xmlrpc'


@args.subcmd(TracOpts)
class Search(args.Search):
    pass
