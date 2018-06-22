from .. import args


class GithubRestOpts(args.ServiceOpts):
    """Github REST API v3 options."""

    _service = 'github-rest'


class Search(args.PagedSearch, GithubRestOpts):
    pass
