from .. import args


class SourceforgeOpts(args.ServiceOpts):

    _service = 'sourceforge'


@args.subcmd(SourceforgeOpts)
class Search(args.Search):
    pass
