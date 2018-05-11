from .. import args


class JiraOpts(args.ServiceOpts):
    """Jira options."""

    _service = 'jira'


@args.subcmd(JiraOpts)
class Search(args.PagedSearch):
    pass
