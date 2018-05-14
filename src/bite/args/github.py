from .. import args


class GithubOpts(args.ServiceOpts):
    """Github options."""

    _service = 'github'


class Search(args.PagedSearch, GithubOpts):
    pass
