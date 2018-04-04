from dateutil.parser import parse as parsetime

from . import Bugzilla

class BugzillaRest(Bugzilla):
    """CLI for Bugzilla REST interface."""

    _service = 'bugzilla-rest'
