import argparse

from . import BugzillaOpts


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


class BugzillaRestOpts(BugzillaOpts):

    _service = 'bugzilla-rest'
