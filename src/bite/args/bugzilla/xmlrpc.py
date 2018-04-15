from . import Bugzilla4_4_Opts, Bugzilla5_0_Opts, Bugzilla5_2_Opts


class Bugzilla4_4XmlrpcOpts(Bugzilla4_4_Opts):

    _service = 'bugzilla4.4-xmlrpc'


class Bugzilla5_0XmlrpcOpts(Bugzilla5_0_Opts):

    _service = 'bugzilla5.0-xmlrpc'


class Bugzilla5_2XmlrpcOpts(Bugzilla5_2_Opts):

    _service = 'bugzilla5.2-xmlrpc'
