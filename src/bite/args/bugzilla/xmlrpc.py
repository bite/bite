from . import Bugzilla4_4Opts, Bugzilla5_0Opts, Bugzilla5_2Opts


class Bugzilla4_4XmlrpcOpts(Bugzilla4_4Opts):
    __doc__ = Bugzilla4_4Opts.__doc__

    _service = 'bugzilla4.4-xmlrpc'


class Bugzilla5_0XmlrpcOpts(Bugzilla5_0Opts):
    __doc__ = Bugzilla5_0Opts.__doc__

    _service = 'bugzilla5.0-xmlrpc'


class Bugzilla5_2XmlrpcOpts(Bugzilla5_2Opts):
    __doc__ = Bugzilla5_2Opts.__doc__

    _service = 'bugzilla5.2-xmlrpc'
