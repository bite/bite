from .. import args


class RedmineOpts(args.ServiceOpts):
    """Redmine options."""


class RedmineElasticOpts(RedmineOpts):
    """Redmine with elasticsearch options."""


class RedmineJsonOpts(RedmineOpts):
    __doc__ = RedmineOpts.__doc__
    _service = 'redmine-json'


class RedmineElasticJsonOpts(RedmineElasticOpts):
    __doc__ = RedmineElasticOpts.__doc__
    _service = 'redmine-elastic-json'


class RedmineXmlOpts(RedmineOpts):
    __doc__ = RedmineOpts.__doc__
    _service = 'redmine-xml'


class RedmineElasticXmlOpts(RedmineElasticOpts):
    __doc__ = RedmineElasticOpts.__doc__
    _service = 'redmine-elastic-xml'


@args.subcmd(RedmineOpts)
class Search(args.PagedSearch):
    pass
