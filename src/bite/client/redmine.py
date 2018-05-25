from . import Cli


class Redmine(Cli):
    """CLI for Redmine service."""


class RedmineJson(Redmine):
    """CLI for Redmine service."""
    _service = 'redmine-json'


class RedmineXml(Redmine):
    """CLI for Redmine service."""
    _service = 'redmine-xml'


class Redmine3_2Json(Redmine):
    """CLI for Redmine 3.2 service."""
    _service = 'redmine3.2-json'


class Redmine3_2Xml(Redmine):
    """CLI for Redmine 3.2 service."""
    _service = 'redmine3.2-xml'


class RedmineElasticJson(RedmineJson):
    """CLI for Redmine service with elasticsearch plugin."""
    _service = 'redmine-elastic-json'


class RedmineElasticXml(RedmineXml):
    """CLI for Redmine service with elasticsearch plugin."""
    _service = 'redmine-elastic-xml'
