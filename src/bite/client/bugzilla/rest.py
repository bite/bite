from . import Bugzilla


class BugzillaRest(Bugzilla):
    """CLI for Bugzilla REST interface."""

    _service = 'bugzilla-rest'
