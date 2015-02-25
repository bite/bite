from bite.cli.bugzilla import Bugzilla

class BugzillaXmlrpc(Bugzilla):
    def __init__(self, **kw):
        super(BugzillaXmlrpc, self).__init__(**kw)
