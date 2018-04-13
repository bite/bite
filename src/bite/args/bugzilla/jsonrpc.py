from . import Bugzilla4_4_Opts, Bugzilla5_0_Opts, BugzillaOpts


class Bugzilla4_4JsonrpcOpts(Bugzilla4_4_Opts):

    _service = 'bugzilla4.4-jsonrpc'


class Bugzilla5_0JsonrpcOpts(Bugzilla5_0_Opts):

    _service = 'bugzilla5.0-jsonrpc'


class BugzillaJsonrpcOpts(BugzillaOpts):

    _service = 'bugzilla-jsonrpc'
