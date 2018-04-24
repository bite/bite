from ... import args


class RedmineOpts(args.ServiceOpts):
    pass


@args.subcmd(RedmineOpts)
class Search(args.PagedSearch):
    pass
