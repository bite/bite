from .. import args


class RedmineOpts(args.ServiceOpts):
    """Redmine options."""


class RedmineJsonOpts(RedmineOpts):
    __doc__ = RedmineOpts.__doc__

    _service = 'redmine-json'


class RedmineXmlOpts(RedmineOpts):
    __doc__ = RedmineOpts.__doc__

    _service = 'redmine-xml'


@args.subcmd(RedmineOpts)
class Search(args.PagedSearch):
    pass
