from .. import args


class RoundupOpts(args.ServiceOpts):

    _service = 'roundup'


@args.subcmd(RoundupOpts)
class Search(args.Search):
    pass


@args.subcmd(RoundupOpts)
class Get(args.Get):
    pass


@args.subcmd(RoundupOpts)
class Attachments(args.Attachments):
    pass


@args.subcmd(RoundupOpts)
class Schema(args.Subcmd):

    def __init__(self, *args, **kw):
        super().__init__(*args, desc='get Roundup db schema', **kw)
