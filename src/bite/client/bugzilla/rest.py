from . import Bugzilla


class Bugzilla5_0Rest(Bugzilla):

    _service = 'bugzilla5.0-rest'


class BugzillaRest(Bugzilla):
    """CLI for Bugzilla REST interface."""

    _service = 'bugzilla-rest'
