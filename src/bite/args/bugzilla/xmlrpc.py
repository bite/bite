from . import Bugzilla4_4Opts, Bugzilla5_0Opts, Bugzilla5_2Opts


class Bugzilla4_4XmlrpcOpts(Bugzilla4_4Opts):

    _service = 'bugzilla4.4-xmlrpc'


class Bugzilla5_0XmlrpcOpts(Bugzilla5_0Opts):

    _service = 'bugzilla5.0-xmlrpc'


class Bugzilla5_2XmlrpcOpts(Bugzilla5_2Opts):

    _service = 'bugzilla5.2-xmlrpc'
