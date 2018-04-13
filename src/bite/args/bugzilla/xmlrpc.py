from . import Bugzilla4_4_Opts, Bugzilla5_0_Opts, BugzillaOpts


class Bugzilla4_4XmlrpcOpts(Bugzilla4_4_Opts):

    _service = 'bugzilla4.4-xmlrpc'


class Bugzilla5_0XmlrpcOpts(Bugzilla5_0_Opts):

    _service = 'bugzilla5.0-xmlrpc'


class BugzillaXmlrpcOpts(BugzillaOpts):

    _service = 'bugzilla-xmlrpc'
