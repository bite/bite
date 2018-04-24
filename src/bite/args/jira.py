from .. import args


class JiraOpts(args.ServiceOpts):

    _service = 'jira'


@args.subcmd(JiraOpts)
class Search(args.PagedSearch):
    pass
