import argparse
import re
import sys

import datetime
from dateutil.parser import parse as parsetime
from dateutil.relativedelta import *

from .. import generic_options
from ...argparser import parse_stdin, string_list, id_list, ids
from ...utc import utc

def parse_bug_list(s):
    try:
        return [int(i) for i in s.split(',')]
    except ValueError:
        msg = '"{}" is not a valid bug id'.format(i)
        raise argparse.ArgumentTypeError(msg)

def parse_date(s):
    today = datetime.datetime.utcnow()
    offset = re.match(r'^(\d+)([ymwdhs]|min)$', s)

    if offset:
        units = {'y': 'years', 'm': 'months', 'w': 'weeks', 'd': 'days',
            'h': 'hours', 'min': 'minutes', 's': 'seconds'}
        unit = units[offset.group(2)]
        value = -int(offset.group(1))
        kw = {unit: value}
        date = today + relativedelta(**kw)
    elif re.match(r'^\d\d\d\d$', s):
        date = parsetime(s) + relativedelta(yearday=1)
    elif re.match(r'^\d\d\d\d[-/]\d\d$', s):
        date = parsetime(s) + relativedelta(day=1)
    elif re.match(r'^(\d\d)?\d\d[-/]\d\d[-/]\d\d$', s):
        date = parsetime(s)
    elif re.match(r'^\d\d\d\d-\d\d-\d\dT\d\d:\d\d:\d\d(\+\d\d:\d\d)?$', s):
        try:
            # try converting timezone if one is specified
            date = parsetime(s).astimezone(utc)
        except ValueError:
            # otherwise default to UTC if none is specified
            date = parsetime(s).replace(tzinfo=utc)
    else:
        msg = '"{}" is not a valid date argument'.format(s)
        raise argparse.ArgumentTypeError(msg)
    return (s, date.isoformat())

def subcmds(subparsers):
    # attach arguments
    parser = subparsers.add_parser('attach',
        description='attach file to bug(s)',
        help='attach file to bug(s)')
    parser.set_defaults(fcn='attach')
    # positional args
    parser.add_argument('filepath',
        type=str,
        help='path of the file to attach')
    parser.add_argument('ids',
        type=id_list,
        action=parse_stdin,
        metavar='ID',
        help='bug ID(s) where the file should be attached')
    # optional args
    parser.add_argument('-c', '--content-type',
        help='mimetype of the file e.g. text/plain (default: auto-detect)')
    parser.add_argument('-p', '--patch',
        action='store_true',
        help='attachment is a patch',
        dest='is_patch')

    # attachment arguments
    parser = subparsers.add_parser(
        'attachment', verbose=False,
        description='get attachment(s)',
        help='get attachment(s)')
    parser.set_defaults(fcn='attachment')
    # positional args
    parser.add_argument('ids',
        type=id_list,
        action=parse_stdin,
        metavar='ID',
        help='attachment ID(s) (or bug ID(s) when --bugid is used)')
    # optional args
    parser.add_argument('-l', '--list',
        action='store_true',
        dest='metadata',
        help='list attachment metadata')
    parser.add_argument('--bugid',
        action='store_true',
        help='search by bug ID(s) rather than attachment ID(s)')

    # changes arguments
    parser = subparsers.add_parser('changes',
        description='get changes from bug(s)',
        help='get changes from bug(s)')
    parser.set_defaults(fcn='changes')
    # positional args
    parser.add_argument('ids',
        type=id_list,
        action=parse_stdin,
        metavar='ID',
        help='ID(s) or alias(es) of the bug(s) to retrieve all changes')
    parser.add_argument('-c', '--created',
        dest='creation_time',
        metavar='TIME',
        type=parse_date,
        action=parse_stdin,
        help='changes made at this time or later')
    parser.add_argument('-m', '--match',
        type=string_list,
        help='restrict by matching changed fields')
    parser.add_argument('-n', '--number',
        dest='change_num',
        type=id_list,
        action=parse_stdin,
        help='restrict by change number(s)')
    parser.add_argument('--output',
        help='custom format for output')
    parser.add_argument('-r', '--creator',
        type=string_list,
        action=parse_stdin,
        help='restrict by person who made the change')

    # comments arguments
    parser = subparsers.add_parser('comments',
        description='get comments from bug(s)',
        help='get comments from bug(s)')
    parser.set_defaults(fcn='comments')
    # positional args
    parser.add_argument('ids',
        type=id_list,
        action=parse_stdin,
        metavar='ID',
        help='ID(s) or alias(es) of the bug(s) to retrieve all comments')
    parser.add_argument('-n', '--number',
        dest='comment_num',
        type=id_list,
        action=parse_stdin,
        help='restrict by comment number(s)')
    parser.add_argument('--output',
        help='custom format for output')
    parser.add_argument('-c', '--created',
        dest='creation_time',
        metavar='TIME',
        type=parse_date,
        help='comments made at this time or later')
    parser.add_argument('-r', '--creator',
        type=string_list,
        action=parse_stdin,
        help='restrict by the email of the person who made the comment')
    parser.add_argument('-a', '--attachment',
        action='store_true',
        help='restrict by comments that include attachments')

    # create arguments
    parser = subparsers.add_parser('create',
        description='create a new bug',
        help='create a new bug')
    parser.set_defaults(fcn='create')
    # optional args
    person = parser.add_argument_group('Person related')
    person.add_argument('-a', '--assigned-to',
        help='assign bug to someone other than the default assignee')
    person.add_argument('--qa-contact',
        help='set the QA Contact for this bug')
    person.add_argument('--cc',
        type=string_list,
        help='add a list of emails to CC list')
    attr = parser.add_argument_group('Attribute related')
    attr.add_argument('-d', '--description',
        help='description of the bug')
    attr.add_argument('-S', '--severity',
        help='set the severity for the new bug')
    attr.add_argument('-s', '--status',
        help='set the status for the new bug')
    attr.add_argument('-t', '--title',
        help='title of bug',
        dest='summary')
    attr.add_argument('-u', '--url',
        help='URL for this bug')
    attr.add_argument('--product',
        help='product')
    attr.add_argument('--component',
        help='component')
    attr.add_argument('--version',
        help='version of the product')
    attr.add_argument('--op-sys',
        help='operating system for this bug')
    attr.add_argument('--platform',
        help='platform for this bug')
    attr.add_argument('--priority',
        help='set priority for the new bug')
    attr.add_argument('--target-milestone',
        help='set a target milestone for this bug')
    attr.add_argument('--alias',
        help='set the alias for this bug')
    attr.add_argument('--groups',
        type=string_list,
        help='list of groups this bug should be put into')
    attr.add_argument('--blocks',
        type=parse_bug_list,
        help='list of bugs this bug blocks')
    attr.add_argument('--depends',
        type=parse_bug_list,
        help='list of bugs this bug depends on')
    attr.add_argument('--keywords',
        type=string_list,
        help='set the keywords of this bug')

    # get arguments
    parser = subparsers.add_parser('get',
        description='get bug(s)',
        help='get bug(s)')
    parser.set_defaults(fcn='get')
    # positional args
    parser.add_argument('ids',
        type=id_list,
        action=parse_stdin,
        metavar='ID',
        help='ID(s) or alias(es) of the bug(s) to retrieve')
    # optional args
    parser.add_argument('--history',
        action='store_true',
        help='show bug history',
        dest='get_history')
    parser.add_argument('--show-obsolete',
        action='store_true',
        help='show obsolete attachments')

    # modify arguments
    parser = subparsers.add_parser(
        'modify', verbose=False,
        description='modify bug(s)',
        help='modify bug(s)')
    parser.set_defaults(fcn='modify')
    # positional args
    parser.add_argument('ids',
        type=id_list,
        action=parse_stdin,
        metavar='ID',
        help='ID(s) of the bug(s) to modify')
    # optional args
    attr = parser.add_argument_group('Attribute related')
    attr.add_argument('-c', '--comment',
        help='add comment from command line',
        metavar='COMMENT',
        dest='comment-body')
    attr.add_argument('-r', '--reply',
        help='reply to a comment')
    attr.add_argument('-R', '--resolution',
        help='set new resolution (only if status = RESOLVED)')
    attr.add_argument('-S', '--severity',
        help='set severity for this bug')
    attr.add_argument('-s', '--status',
        help='set new status of bug (e.g. RESOLVED)')
    attr.add_argument('-t', '--title',
        help='set title of bug',
        dest='summary')
    attr.add_argument('-u', '--url',
        help='set URL field of bug')
    attr.add_argument('-v', '--version',
        help='set the version for this bug'),
    attr.add_argument('-w', '--whiteboard',
        help='set status whiteboard'),
    attr.add_argument('--alias',
        help='change the alias for this bug')
    attr.add_argument('--add-blocks',
        type=id_list,
        help='add a bug to the blocked list',
        metavar='BUG_ID',
        dest='blocks-add')
    attr.add_argument('--remove-blocks',
        type=id_list,
        help='remove a bug from the blocked list',
        metavar='BUG_ID',
        dest='blocks-remove')
    attr.add_argument('--component',
        help='change the component for this bug')
    attr.add_argument('--add-depends',
        type=id_list,
        help='add a bug to the depends list',
        metavar='BUG_ID',
        dest='depends_on-add')
    attr.add_argument('--remove-depends',
        type=id_list,
        help='remove a bug from the depends list',
        metavar='BUG_ID',
        dest='depends_on-remove')
    attr.add_argument('--add-groups',
        type=string_list,
        help='add a group to this bug',
        metavar='GROUP',
        dest='groups-add')
    attr.add_argument('--remove-groups',
        type=string_list,
        help='remove a group from this bug',
        metavar='GROUP',
        dest='groups-remove')
    attr.add_argument('--keywords',
        type=string_list,
        help='set the keywords of this bug',
        metavar='KEYWORDS',
        dest='keywords-set')
    attr.add_argument('--add-keywords',
        type=string_list,
        help='add a keyword to the bug',
        metavar='KEYWORD',
        dest='keywords-add')
    attr.add_argument('--remove-keywords',
        type=string_list,
        help='remove a keyword from this bug',
        metavar='KEYWORD',
        dest='keywords-remove')
    attr.add_argument('--target-milestone',
        help='set a target milestone for this bug')
    attr.add_argument('--op-sys',
        help='change the operating system for this bug')
    attr.add_argument('--platform',
        help='change the platform for this bug')
    attr.add_argument('--priority',
        help='change the priority for this bug')
    attr.add_argument('--product',
        help='change the product for this bug')
    attr.add_argument('--add-see-also',
        type=string_list,
        help='add a "see also" URL to this bug',
        metavar='URL',
        dest='see_also-add')
    attr.add_argument('--remove-see-also',
        type=string_list,
        help='remove a "see also" URL from this bug',
        metavar='URL',
        dest='see_also-remove')
    person = parser.add_argument_group('Person related')
    person.add_argument('-a', '--assigned-to',
        help='change assignee for this bug')
    person.add_argument('--add-cc',
        type=string_list,
        help='add emails to the CC list',
        dest='cc-add')
    person.add_argument('--remove-cc',
        type=string_list,
        help='remove emails from the CC list',
        dest='cc-remove')
    person.add_argument('--qa-contact',
        help='change the QA contact for this bug')
    status = parser.add_argument_group('Status related')
    status.add_argument('-d', '--duplicate',
        type=int,
        help='mark bug as a duplicate',
        metavar='BUG_ID',
        dest='dupe_of')
    status.add_argument('--fixed',
        action='store_true',
        help='mark bug as RESOLVED, FIXED')
    status.add_argument('--invalid',
        action='store_true',
        help='mark bug as RESOLVED, INVALID')
    time = parser.add_argument_group('Time related')
    time.add_argument('--deadline',
        help='change the deadline for this bug')
    time.add_argument('--estimated-time',
        metavar='TIME',
        help='change the estimated time for this bug')
    time.add_argument('--remaining-time',
        metavar='TIME',
        help='change the remaining time for this bug')
    time.add_argument('--work-time',
        metavar='TIME',
        help='set number of hours worked on this bug as part of this change'),

    # query arguments
    parser = subparsers.add_parser('query',
        description='query bugzilla for various data',
        help='query bugzilla for various data')
    parser.set_defaults(fcn='query')
    # positional args
    parser.add_argument('queries',
        action=parse_stdin,
        nargs='*',
        help='raw queries to perform on bugzilla of the format "method[#params]" '
            '(e.g. use "Bug.get#{\'ids\': [100]}" to get bug 100)')
    # optional args
    parser.add_argument('--bugzilla-version',
        action='store_true',
        help='get the version of bugzilla')
    parser.add_argument('--raw',
        action='store_true',
        help='print raw, unformatted json responses')
    parser.add_argument('--bugzilla-extensions',
        action='store_true',
        help='get the extensions of bugzilla')
    parser.add_argument('--products',
        action='append',
        help='get the info for products matching the given information (either ID or name')
    parser.add_argument('-f', '--fields',
        action='append',
        nargs='?',
        help='get the info for fields matching the given information (either ID or name')
    parser.add_argument('--users',
        action='append',
        help='get the info for users matching the given information (either ID, login, or matching string')

    # search arguments
    parser = subparsers.add_parser(
        'search', verbose=False,
        description='search for bugs',
        help='search for bugs')
    parser.set_defaults(fcn='search')
    # positional args
    parser.add_argument('terms',
        action=parse_stdin,
        nargs='*',
        help='strings to search for in title and/or body')
    # optional args
    parser.add_argument('--output',
        help='custom format for search output')
    person = parser.add_argument_group('Person related')
    person.add_argument('-a', '--assigned-to',
        type=string_list,
        action=parse_stdin,
        help='email of the person the bug is assigned to')
    person.add_argument('-r', '--creator',
        type=string_list,
        action=parse_stdin,
        help='email of the person who created the bug')
    person.add_argument('--qa-contact',
        help='email of the QA contact for the bug')
    time = parser.add_argument_group('Time related')
    time.add_argument('-c', '--created',
        dest='creation_time',
        metavar='TIME',
        type=parse_date,
        action=parse_stdin,
        help='bugs created at this time or later')
    time.add_argument('-m', '--modified',
        dest='last_change_time',
        metavar='TIME',
        type=parse_date,
        action=parse_stdin,
        help='bugs modified at this time or later')
    attr = parser.add_argument_group('Attribute related')
    attr.add_argument('-s', '--status',
        type=string_list,
        action=parse_stdin,
        help='restrict by status (one or more)')
    attr.add_argument('-v', '--version',
        type=string_list,
        action=parse_stdin,
        help='restrict by version (one or more)')
    attr.add_argument('-w', '--whiteboard',
        type=string_list,
        action=parse_stdin,
        help='status whiteboard')
    attr.add_argument('--alias',
        type=string_list,
        action=parse_stdin,
        help='unique alias for this bug')
    attr.add_argument('--component',
        type=string_list,
        action=parse_stdin,
        help='restrict by component (one or more)')
    attr.add_argument('--id',
        type=id_list,
        action=parse_stdin,
        help='restrict by bug ID(s)')
    attr.add_argument('--op-sys',
        type=string_list,
        action=parse_stdin,
        help='restrict by operating system (one or more)')
    attr.add_argument('--platform',
        type=string_list,
        action=parse_stdin,
        help='restrict by platform (one or more)')
    attr.add_argument('--priority',
        type=string_list,
        action=parse_stdin,
        help='restrict by priority (one or more)')
    attr.add_argument('--product',
        type=string_list,
        action=parse_stdin,
        help='restrict by product (one or more)')
    attr.add_argument('--resolution',
        type=string_list,
        action=parse_stdin,
        help='restrict by resolution')
    attr.add_argument('--severity',
        type=string_list,
        action=parse_stdin,
        help='restrict by severity (one or more)')
    attr.add_argument('--target-milestone',
        type=string_list,
        action=parse_stdin,
        help='restrict by target milestone (one or more)')

    # add generic options for subcommands
    get_actions = ['get', 'search', 'comments', 'changes']
    send_actions = ['attach', 'modify', 'create']
    generic_options(subparsers, get_actions, send_actions)
