import argparse

from . import parse_date
from .. import *
from ...argparser import parse_stdin, string_list, id_list, ids

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

def subcmds(subparsers):
    # version cmd
    parser = subparsers.add_parser('version', help='get bugzilla version')
    parser.set_defaults(fcn='version')

    # extensions cmd
    parser = subparsers.add_parser('extensions', help='get bugzilla extensions')
    parser.set_defaults(fcn='extensions')

    # fields cmd
    parser = subparsers.add_parser('fields', help='get bugzilla fields')
    parser.set_defaults(fcn='fields')
    # positional args
    parser.add_argument('fields',
        type=string_list,
        action=parse_stdin,
        nargs='?',
        help='either ID or name')

    # users cmd
    parser = subparsers.add_parser('users', help='get bugzilla users')
    parser.set_defaults(fcn='users')
    # positional args
    parser.add_argument('users',
        action=parse_stdin,
        nargs='+',
        help='either ID, login, or matching string')

    #attach_parser(subparsers)
    #attachment_parser(subparsers)
    #get_parser(subparsers)
    #modify_parser(subparsers)
    #post_parser(subparsers)
    #search_parser(subparsers)

    # parser = subparsers.add_parser('search',
    #     help='search for bugs')
    # parser.add_argument('terms',
    #     nargs='*',
    #     help='strings to search for in title and/or body')
    # parser.add_argument('--alias',
    #     action='append',
    #     help='The unique alias for this bug')
    # parser.add_argument('-a', '--assigned-to',
    #     type=person_search,
    #     action='append',
    #     help='email of the person the bug is assigned to')
    # parser.add_argument('-r', '--creator',
    #     type=person_search,
    #     action='append',
    #     help='email of the person who created the bug')
    # parser.add_argument('--cc',
    #     type=person_search,
    #     action='append',
    #     help='email of the person who is CCed on the bug')
    # parser.add_argument('--commenter',
    #     type=person_search,
    #     action='append',
    #     help='email of the person who commented on the bug')
    # parser.add_argument('--qa-contact',
    #     help='email of the QA contact for the bug')
    # parser.add_argument('-c', '--created',
    #     dest='creation_time',
    #     type=parse_date,
    #     help='bugs created at this time or later')
    # parser.add_argument('-m', '--modified',
    #     dest='last_change_time',
    #     type=parse_date,
    #     help='bugs modified at this time or later')
    # parser.add_argument('--changed-after',
    #     help='bugs changed at this time or later')
    # parser.add_argument('--changed-before',
    #     help='bugs changed at this time or before')
    # parser.add_argument('--changed-field',
    #     type=string_list,
    #     action='append',
    #     help='bug field that changed')
    # parser.add_argument('--changed-to',
    #     help='value that bug field changed to')
    # parser.add_argument('--fields',
    #     type=string_list,
    #     metavar='FIELD | "FIELD FIELD ..."',
    #     help='fields to output (default: "id assigned_to summary")')
    # parser.add_argument('-l', '--limit',
    #     type=int,
    #     help='Limit the number of records returned in a search')
    # parser.add_argument('--offset',
    #     type=int,
    #     help='Set the start position for a search')
    # parser.add_argument('--op-sys',
    #     action='append',
    #     help='restrict by operating system (one or more)')
    # parser.add_argument('--platform',
    #     action='append',
    #     help='restrict by platform (one or more)')
    # parser.add_argument('--priority',
    #     action='append',
    #     help='restrict by priority (one or more)')
    # parser.add_argument('--component',
    #     action='append',
    #     help='restrict by component (one or more)')
    # parser.add_argument('--product',
    #     action='append',
    #     help='restrict by product (one or more)')
    # parser.add_argument('--resolution',
    #     action='append',
    #     help='restrict by resolution')
    # parser.add_argument('--severity',
    #     action='append',
    #     help='restrict by severity (one or more)')
    # parser.add_argument('--target-milestone',
    #     action='append',
    #     help='restrict by target milestone (one or more)')
    # parser.add_argument('-s', '--status',
    #     action='append',
    #     help='restrict by status (one or more, use all for all statuses)')
    # parser.add_argument('-v', '--version',
    #     action='append',
    #     help='restrict by version (one or more)')
    # parser.add_argument('-w', '--whiteboard',
    #     action='append',
    #     help='status whiteboard')
    # parser.add_argument('--sort',
    #     dest='order',
    #     choices=['id', 'importance', 'assignee', 'modified'],
    #     help='method to sort the results by (defaults to bug number)')
    # parser.add_argument('--save',
    #     dest='save_search',
    #     metavar='SEARCH_ALIAS',
    #     help='save this search to an alias')
    # parser.add_argument('--load',
    #     dest='load_search',
    #     metavar='SEARCH_ALIAS',
    #     help='run a saved search')
    # parser.add_argument('-n', '--dry-run',
    #     action='store_true',
    #     help='show what would be searched for')
    # parser.set_defaults(fcn='search')
