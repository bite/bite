import argparse
import re

import datetime
from dateutil.parser import parse as parsetime
from dateutil.relativedelta import *

from ..argparser import parse_stdin, string_list, id_list, ids

def subcmds(subparsers):
    # modification related methods not supported yet

    parser = subparsers.add_parser('attachment',
        help='get an attachment')
    parser.set_defaults(fcn='attachment')
    # positional args
    parser.add_argument('ids',
        type=attachment_id,
        action=parse_stdin,
        nargs='+',
        help='the ID(s) of the attachment(s)')
    # optional args
    attachment = base_options(parser, 'attachment')

    parser = subparsers.add_parser('get',
        help='get an issue')
    parser.set_defaults(fcn='get')
    # positional args
    parser.add_argument('ids',
        type=ids,
        action=parse_stdin,
        nargs='+',
        metavar='ID',
        help='the ID(s) of the issues(s) to retrieve')
    # optional args
    get = base_options(parser, 'get')
    get.add_argument('--no-updates',
        action='store_false',
        default=True,
        help='do not show updates to fields like labels, status, owner, ...',
        dest='get_updates')

    parser = subparsers.add_parser('search',
        help='search for issues')
    parser.set_defaults(fcn='search')
    # positional args
    parser.add_argument('terms',
        action=parse_stdin,
        nargs='*',
        help='strings to search for in title and/or body')
    # optional args
    search = base_options(parser, 'search')
    search.add_argument('--has',
        choices=['attachment', 'no-attachment', 'cc', 'no-cc', 'owner', 'no-owner',
                'comment', 'no-comment', 'label', 'no-label', 'status', 'no-status',
                'type', 'no-type'],
        action='append',
        help="restrict by issues that have or don't have a specified field")
    search.add_argument('--attachment',
        help='restrict by issues that have attachments matching a certain filename')
    search.add_argument('--blocked',
        action='store_true',
        help='restrict by issues that are blocked')
    search.add_argument('--blocked-on',
        action='append',
        type=int,
        help='restrict by blocked on issues (one or more)')
    search.add_argument('--blocking',
        action='append',
        type=int,
        help='restrict by blocking issues (one or more)')
    search.add_argument('-o', '--owner',
        help='owner of the issue (or none for no owner)')
    search.add_argument('-r', '--reporter',
        help='restrict by reporter')
    search.add_argument('--cc',
        action='append',
        help='restrict by CC email address (one or more)')
    search.add_argument('--commenter',
        action='append',
        help='restrict by commenter email address (one or more)')
    search.add_argument('-s', '--status',
        action='append',
        help='restrict by status (one or more, use all for all statuses)')
    search.add_argument('-l', '--label',
        action='append',
        help='restrict by label (one or more)')
    search.add_argument('--attr',
        type=attribute,
        action='append',
        help='restrict by attribute and value (one or more of type attr:value)')
    search.add_argument('-t', '--type',
        action='append',
        help='restrict by type (one or more)')
    search.add_argument('--milestone',
        action='append',
        help='restrict by milestone (one or more)')
    search.add_argument('--opened',
        type=parse_dates,
        help='restrict by opened date')
    search.add_argument('--modified',
        type=parse_dates,
        help='restrict by last modified date')
    search.add_argument('--closed',
        type=parse_dates,
        help='restrict by closed date')
    search.add_argument('--published',
        type=parse_dates2,
        help='restrict by published date')
    search.add_argument('--updated',
        type=parse_dates2,
        help='restrict by updated date')
    search.add_argument('--stars',
        type=parse_stars,
        help='restrict by number of stars')
    search.add_argument('--summary',
        action='store_true',
        help='search in the issue summary')
    search.add_argument('--description',
        action='store_true',
        help='search in the issue description')
    search.add_argument('--comment',
        action='store_true',
        help='search in the issue comments')
    search.add_argument('--query',
        help='manually specify an advanced query')
    search.add_argument('--sort',
        #choices=service.attributes.keys() + ['-' + key for key in service.attributes.keys()],
        help='sort by field type')
    search.add_argument('-u', '--url',
        action='store_true',
        help='show search url for the browser')
    search.add_argument('--output',
        type=str,
        help='custom format for search output')

    # # add generic options for subcommands
    # get_actions = [get, search]
    # send_actions = []
    #
    # for group in get_actions:
    #     generic_receive(group)
    # for group in send_actions:
    #     generic_send(group)


def modify(subparsers):
    parser = subparsers.add_parser('modify',
        help='modify an issue (eg. post a comment)')
    parser.add_argument('issue_id',
        type=int,
        help='the ID of the issue to modify')
    # optional args
    parser.add_argument('-c', '--comment',
        help='add comment from command line')
    parser.add_argument('-d', '--duplicate',
        type=int,
        help='this issue is a duplicate')
    parser.add_argument('-o', '--owner',
        help='change owner for this issue')
    parser.add_argument('-t', '--title',
        help='set title of issue')
    parser.add_argument('-u', '--url',
        help='set URL field of issue')
    parser.add_argument('--add-cc',
        action='append',
        help='add an email to the CC list')
    parser.add_argument('--remove-cc',
        action='append',
        help='remove an email from the CC list')
    parser.add_argument('--add-depends',
        action='append',
        help='add an issue to the depends list')
    parser.add_argument('--remove-depends',
        action='append',
        help='remove an issue from the depends list')
    parser.add_argument('--add-blocked',
        action='append',
        help='add an issue to the blocked list')
    parser.add_argument('--remove-blocked',
        action='append',
        help='remove an issue from the blocked list')
    parser.add_argument('--fixed',
        action='store_true',
        help='mark issue as fixed')
    parser.add_argument('--invalid',
        action='store_true',
        help='mark issue as invalid')
    parser.set_defaults(fcn='modify')

def create(subparsers):
    parser = subparsers.add_parser('create',
        help='create a new issue')
    # optional args
    parser.add_argument('-t', '--title',
        help='title of issue')
    parser.add_argument('-d', '--description',
        help='description of the issue')
    parser.add_argument('-o', '--owner',
        help='change owner for this issue')
    parser.add_argument('--cc',
        help='add a list of emails to CC list')
    parser.add_argument('-u', '--url',
        help='URL associated with the issue')
    parser.add_argument('--depends-on',
        help='add a list of issue dependencies',
        dest='dependson')
    parser.add_argument('--blocked',
        help='add a list of blocker issues')
    parser.set_defaults(fcn='create')

def parse_stars(s):
    rg = re.match(r'^(\d+)-(\d+)$', s)
    gt = re.match(r'^(\d+)-$', s)
    lt = re.match(r'^-(\d+)$', s)
    eq = re.match(r'^\d+(,\d+)*$', s)

    if rg:
        (lower, upper) = rg.groups()
        lower = int(lower)
        upper = int(upper)+1
        stars_query = 'stars:{} -stars:{}'.format(lower, upper)
    elif gt:
        bound = int(gt.group(1))
        stars_query = 'stars:{}'.format(bound)
    elif lt:
        bound = int(lt.group(1))+1
        stars_query = 'stars:0 -stars:{}'.format(bound)
    elif eq:
        stars_query = [x for x in s.split(',')]
    else:
        msg = '{} is not a valid stars argument'.format(s)
        raise argparse.ArgumentTypeError(msg)

    return (s, stars_query)

def isodate(date):
    return date.strftime('%Y-%m-%d')

def oneday(day):
    next_day = day + relativedelta(days=+1)
    return (isodate(day), isodate(next_day))

def parse_date(string):
    if re.match(r'^\d\d\d\d$', string):
        temp_date = dateutil.parser.parse(string)
        lower = temp_date + relativedelta(nlyearday=365, years=-1)
        upper = temp_date + relativedelta(nlyearday=1, years=+1)
        date_range = (isodate(lower), isodate(upper))
    elif re.match(r'^\d\d\d\d/\d\d$', string):
        temp_date = dateutil.parser.parse(string)
        lower = temp_date + relativedelta(day=31, months=-1)
        upper = temp_date + relativedelta(day=1, months=+1)
        date_range = (isodate(lower), isodate(upper))
    elif re.match(r'^\d\d\d\d/\d\d/\d\d$', string):
        temp_date = dateutil.parser.parse(string)
        lower = temp_date + relativedelta(days=-1)
        upper = temp_date + relativedelta(days=+1)
        date_range = (isodate(lower), isodate(upper))
    else:
        return None

    return date_range

def parse_dates(string):
    days = { 'mon': MO, 'tue': TU, 'wed': WE, 'thu': TH, 'fri': FR, 'sat': SA, 'sun': SU }
    today = datetime.datetime.utcnow()
    tomorrow = today + relativedelta(days=+1)

    upper_bound = re.match(r'^-(\d\d\d\d(/\d\d){0,2})$', string)
    lower_bound = re.match(r'^(\d\d\d\d(/\d\d){0,2})-$', string)
    range = re.match(r'^(\d\d\d\d(/\d\d){0,2})-(\d\d\d\d(/\d\d){0,2})$', string)

    offset = re.match(r'^([<=>])(\d+)([ymwd])$', string)

    temp_range = parse_date(string)
    if temp_range is not None:
        date_range = temp_range
    elif upper_bound:
        (lower, upper) = parse_date(upper_bound.group(1))
        date_range = (None, upper)
    elif lower_bound:
        (lower, upper) = parse_date(lower_bound.group(1))
        date_range = (lower, None)
    elif range:
        (lower1, upper1) = parse_date(range.group(1))
        (lower2, upper2) = parse_date(range.group(3))
        date_range = (lower1, upper2)
    elif offset:
        units = {'y': 'years', 'm': 'months', 'w': 'weeks', 'd': 'days'}
        unit = units[offset.group(3)]
        value = -int(offset.group(2))
        kw = {unit: value}
        operator = offset.group(1)

        if operator == '<':
            date = today + relativedelta(**kw)
            lower_bound = isodate(date)
            date_range = (lower_bound, None)
        elif operator == '=':
            date = today + relativedelta(**kw)
            date_range = oneday(date)
        elif operator == '>':
            date = today + relativedelta(**kw)
            upper_bound = isodate(date)
            date_range = (None, upper_bound)

    elif string.lower() in days:
        day = today + relativedelta(weekday=days[string.lower()](-1))
        date_range = oneday(day)
    elif string == 'today':
        date_range = oneday(today)
    elif string == 'yesterday':
        yesterday = today + relativedelta(days=-1)
        date_range = oneday(yesterday)
    elif string == 'this-week':
        monday = today + relativedelta(weekday=MO(-1))
        sunday = today + relativedelta(weekday=SU)
        this_monday = isodate(monday)
        this_sunday = isodate(sunday)
        date_range = (this_monday, this_sunday)
    elif string == 'last-week':
        monday = today + relativedelta(days=-1, weekday=MO(-2))
        sunday = today + relativedelta(days=-1, weekday=SU(-1))
        last_monday = isodate(monday)
        last_sunday = isodate(sunday)
        date_range = (last_monday, last_sunday)
    elif string == 'this-month':
        this_month = today + relativedelta(day=1)
        date_range = (isodate(this_month), isodate(tomorrow))
    elif string == 'last-month':
        last_month = today + relativedelta(day=1, months=-1)
        this_month = today + relativedelta(day=1)
        date_range = (isodate(last_month), isodate(this_month))
    else:
        msg = '{} is not a valid date argument'.format(string)
        raise argparse.ArgumentTypeError(msg)

    return (string, date_range)

def parse_dates2(string):
    days = { 'mon': MO, 'tue': TU, 'wed': WE, 'thu': TH, 'fri': FR, 'sat': SA, 'sun': SU }
    today = datetime.datetime.utcnow()
    tomorrow = today + relativedelta(days=+1)

    upper_bound = re.match(r'^-(\d\d\d\d(/\d\d){0,2})$', string)
    lower_bound = re.match(r'^(\d\d\d\d(/\d\d){0,2})-$', string)
    range = re.match(r'^(.+)-(.+)$', string)

    offset = re.match(r'^([<=>])(\d+)([ymwdhs]|min)$', string)

    if range:
        lower = dateutil.parser.parse(range.group(1))
        upper = dateutil.parser.parse(range.group(2))
        date_range = (datetimetostr(lower), datetimetostr(upper))
    elif offset:
        units = {'y': 'years', 'm': 'months', 'w': 'weeks', 'd': 'days',
            'h': 'hours', 'min': 'minutes', 's': 'seconds'}
        unit = units[offset.group(3)]
        value = -int(offset.group(2))
        kwargs = {unit: value}
        operator = offset.group(1)

        if operator == '<':
            date = today + relativedelta(**kwargs)
            lower_bound = datetimetostr(date)
            date_range = (lower_bound, None)
        #elif operator == '=':
            #date = today + relativedelta(**kwargs)
            #date_range = oneday(date)
        elif operator == '>':
            date = today + relativedelta(**kwargs)
            upper_bound = datetimetostr(date)
            date_range = (None, upper_bound)

    elif string.lower() in days:
        day = today + relativedelta(weekday=days[string.lower()](-1))
        date_range = oneday(day)
    elif string == 'today':
        date_range = oneday(today)
    elif string == 'yesterday':
        yesterday = today + relativedelta(days=-1)
        date_range = oneday(yesterday)
    elif string == 'this-week':
        monday = today + relativedelta(weekday=MO(-1))
        sunday = today + relativedelta(weekday=SU)
        this_monday = isodate(monday)
        this_sunday = isodate(sunday)
        date_range = (this_monday, this_sunday)
    elif string == 'last-week':
        monday = today + relativedelta(days=-1, weekday=MO(-2))
        sunday = today + relativedelta(days=-1, weekday=SU(-1))
        last_monday = isodate(monday)
        last_sunday = isodate(sunday)
        date_range = (last_monday, last_sunday)
    elif string == 'this-month':
        this_month = today + relativedelta(day=1)
        date_range = (isodate(this_month), isodate(tomorrow))
    elif string == 'last-month':
        last_month = today + relativedelta(day=1, months=-1)
        this_month = today + relativedelta(day=1)
        date_range = (isodate(last_month), isodate(this_month))
    else:
        msg = '{} is not a valid date argument'.format(string)
        raise argparse.ArgumentTypeError(msg)

    return (string, date_range)

def attribute(string):
    m = re.match(r'^\w+:\w+$', string)
    if m:
        return string
    else:
        msg = '{} is not a valid attr argument'.format(string)
        raise argparse.ArgumentTypeError(msg)

def attachment_id(string):
    m = re.match(r'^\d+-\d+$', string)
    if m:
        return string
    else:
        msg = '{} is not a valid attachment ID'.format(string)
        raise argparse.ArgumentTypeError(msg)
