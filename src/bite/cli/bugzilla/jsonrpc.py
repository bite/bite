from bite.cli.bugzilla import Bugzilla

class BugzillaJsonrpc(Bugzilla):
    def __init__(self, **kw):
        super().__init__(**kw)
