from . import Cli


class Redmine(Cli):
    """CLI for Redmine service."""


class RedmineJson(Redmine):
    """CLI for Redmine service."""

    _service = 'redmine-json'


class RedmineElasticJson(RedmineJson):
    """CLI for Redmine service with elasticsearch plugin."""

    _service = 'redmine-elastic-json'


class RedmineXml(Redmine):
    """CLI for Redmine service."""

    _service = 'redmine-xml'


class RedmineElasticXml(RedmineXml):
    """CLI for Redmine service with elasticsearch plugin."""

    _service = 'redmine-elastic-xml'
