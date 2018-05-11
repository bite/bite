from . import Bugzilla4_4Opts, Bugzilla5_0Opts, Bugzilla5_2Opts


class Bugzilla4_4JsonrpcOpts(Bugzilla4_4Opts):

    _service = 'bugzilla4.4-jsonrpc'


class Bugzilla5_0JsonrpcOpts(Bugzilla5_0Opts):

    _service = 'bugzilla5.0-jsonrpc'


class Bugzilla5_2JsonrpcOpts(Bugzilla5_2Opts):

    _service = 'bugzilla5.2-jsonrpc'
