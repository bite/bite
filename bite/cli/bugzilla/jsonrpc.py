from bite.cli.bugzilla import Bugzilla

class BugzillaJsonrpc(Bugzilla):
    def __init__(self, **kw):
        super(BugzillaJsonrpc, self).__init__(**kw)
