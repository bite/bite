import argparse

from . import Bugzilla5_0_Opts, Bugzilla5_2_Opts


def person_search(s):
    strings = s.split()
    error = None
    if len(strings) > 2:
        error = '"{}" contains too many arguments'.format(s)

    if len(strings) == 1:
        search_type = 'contains'
        name = strings[0]
    else:
        search_type = strings[0]
        name = strings[1]

    if error is not None:
        raise argparse.ArgumentTypeError(error)
    else:
        return (search_type, name)


class Bugzilla5_0RestOpts(Bugzilla5_0_Opts):

    _service = 'bugzilla5.0-rest'


class Bugzilla5_2RestOpts(Bugzilla5_2_Opts):

    _service = 'bugzilla5.2-rest'
