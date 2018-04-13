import argparse
import datetime
from functools import partial
import re
import sys

from dateutil.parser import parse as parsetime
from dateutil.relativedelta import *

from ... import args
from ...argparser import parse_stdin, string_list, id_list, ids
from ...objects import DateTime
from ...utc import utc
from ...utils import str2bool


def parse_date(s):
    today = datetime.datetime.utcnow()
    offset = re.match(r'^(\d+)([ymwdhs]|min)$', s)

    if offset:
        units = {
            'y': 'years',
            'm': 'months',
            'w': 'weeks',
            'd': 'days',
            'h': 'hours',
            'min': 'minutes',
            's': 'seconds',
        }
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
        raise ValueError(f'invalid date argument: {s!r}')

    return date


def date(s):
    if sys.stdin.isatty() or s != '-':
        try:
            return DateTime(s, parse_date(s))
        except ValueError as e:
            raise argparse.ArgumentTypeError(e)
    else:
        return s


class BugzillaOpts(args.ServiceOpts):

    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        self.config_map.update({
            'max_results': int,
            'restrict_login': str2bool,
        })

    def main_opts(self):
        """Add service specific arguments."""
        from ...scripts.bite import auth_opts
        auth_opts.add_argument(
            '--restrict', action='store_true', dest='restrict_login',
            help='restrict the login to your IP address')


@args.subcmd(BugzillaOpts)
class Attach(args.Attach):

    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        # positional args
        self.parser.add_argument(
            'filepath', type=str,
            help='path of the file to attach')
        self.parser.add_argument(
            'ids', type=id_list, metavar='ID',
            action=partial(parse_stdin, ids),
            help='bug ID(s) where the file should be attached')

        # optional args
        self.opts.add_argument(
            '-c', '--content-type',
            help='mimetype of the file e.g. text/plain (default: auto-detect)')
        self.opts.add_argument(
            '-p', '--patch', action='store_true', dest='is_patch',
            help='attachment is a patch')


@args.subcmd(BugzillaOpts)
class Attachments(args.Attachments):

    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        # optional args
        self.opts.add_argument(
            '-l', '--list', action='store_true', dest='show_metadata',
            help='list attachment metadata')


@args.subcmd(BugzillaOpts)
class Create(args.Create):

    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        # optional args
        person = self.parser.add_argument_group('Person related')
        person.add_argument(
            '-a', '--assigned-to',
            help='assign bug to someone other than the default assignee')
        person.add_argument(
            '--qa-contact',
            help='set the QA Contact for this bug')
        person.add_argument(
            '--cc', type=string_list,
            help='add a list of emails to CC list')
        attr = self.parser.add_argument_group('Attribute related')
        attr.add_argument(
            '-d', '--description',
            help='description of the bug')
        attr.add_argument(
            '-S', '--severity',
            help='set the severity for the new bug')
        attr.add_argument(
            '-s', '--status',
            help='set the status for the new bug')
        attr.add_argument(
            '-t', '--title', dest='summary',
            help='title of bug')
        attr.add_argument(
            '-u', '--url',
            help='URL for this bug')
        attr.add_argument(
            '--product',
            help='product')
        attr.add_argument(
            '-C', '--component',
            help='component')
        attr.add_argument(
            '--version',
            help='version of the product')
        attr.add_argument(
            '--op-sys',
            help='operating system for this bug')
        attr.add_argument(
            '--platform',
            help='platform for this bug')
        attr.add_argument(
            '--priority',
            help='set priority for the new bug')
        attr.add_argument(
            '--target-milestone',
            help='set a target milestone for this bug')
        attr.add_argument(
            '--alias',
            help='set the alias for this bug')
        attr.add_argument(
            '--groups', type=string_list,
            help='list of groups this bug should be put into')
        attr.add_argument(
            '--blocks', type=id_list,
            help='list of bugs this bug blocks')
        attr.add_argument(
            '--depends', type=id_list,
            help='list of bugs this bug depends on')
        attr.add_argument(
            '-K', '--keywords', type=string_list,
            help='set the keywords of this bug')


@args.subcmd(BugzillaOpts)
class Get(args.Get):

    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        # optional args
        self.opts.add_argument(
            '-H', '--no-history', dest='get_history', action='store_false',
            help='do not bug history')
        self.opts.add_argument(
            '--show-obsolete', action='store_true',
            help='show obsolete attachments')


@args.subcmd(BugzillaOpts)
class Modify(args.Modify):

    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        # optional args
        attr = self.parser.add_argument_group('Attribute related')
        attr.add_argument(
            '-c', '--comment', metavar='COMMENT', dest='comment-body',
            help='add comment from command line')
        attr.add_argument(
            '-R', '--resolution',
            help='set new resolution (only if status = RESOLVED)')
        attr.add_argument(
            '-S', '--severity',
            help='set severity for this bug')
        attr.add_argument(
            '-s', '--status',
            help='set new status of bug (e.g. RESOLVED)')
        attr.add_argument(
            '-t', '--title', dest='summary',
            help='set title of bug')
        attr.add_argument(
            '-u', '--url',
            help='set URL field of bug')
        attr.add_argument(
            '-v', '--version',
            help='set the version for this bug'),
        attr.add_argument(
            '-w', '--whiteboard',
            help='set status whiteboard'),
        attr.add_argument(
            '--alias',
            help='change the alias for this bug')
        attr.add_argument(
            '--add-blocks', type=id_list,
            metavar='BUG_ID', dest='blocks-add',
            help='add a bug to the blocked list')
        attr.add_argument(
            '--remove-blocks', type=id_list,
            metavar='BUG_ID', dest='blocks-remove',
            help='remove a bug from the blocked list')
        attr.add_argument(
            '--component',
            help='change the component for this bug')
        attr.add_argument(
            '--add-depends', type=id_list,
            metavar='BUG_ID', dest='depends_on-add',
            help='add a bug to the depends list')
        attr.add_argument(
            '--remove-depends', type=id_list,
            metavar='BUG_ID', dest='depends_on-remove',
            help='remove a bug from the depends list')
        attr.add_argument(
            '--add-groups', type=string_list,
            metavar='GROUP', dest='groups-add',
            help='add a group to this bug')
        attr.add_argument(
            '--remove-groups', type=string_list,
            metavar='GROUP', dest='groups-remove',
            help='remove a group from this bug')
        attr.add_argument(
            '-K', '--keywords', type=string_list,
            metavar='KEYWORDS', dest='keywords-set',
            help='set the keywords of this bug')
        attr.add_argument(
            '--add-keywords', type=string_list,
            metavar='KEYWORD', dest='keywords-add',
            help='add a keyword to the bug')
        attr.add_argument(
            '--remove-keywords', type=string_list,
            metavar='KEYWORD', dest='keywords-remove',
            help='remove a keyword from this bug')
        attr.add_argument(
            '--target-milestone',
            help='set a target milestone for this bug')
        attr.add_argument(
            '--op-sys',
            help='change the operating system for this bug')
        attr.add_argument(
            '--platform',
            help='change the platform for this bug')
        attr.add_argument(
            '--priority',
            help='change the priority for this bug')
        attr.add_argument(
            '--product',
            help='change the product for this bug')
        attr.add_argument(
            '--add-see-also', type=string_list,
            metavar='URL', dest='see_also-add',
            help='add a "see also" URL to this bug')
        attr.add_argument(
            '--remove-see-also', type=string_list,
            metavar='URL', dest='see_also-remove',
            help='remove a "see also" URL from this bug')
        person = self.parser.add_argument_group('Person related')
        person.add_argument(
            '-a', '--assigned-to',
            help='change assignee for this bug')
        person.add_argument(
            '--add-cc', type=string_list, dest='cc-add',
            help='add emails to the CC list')
        person.add_argument(
            '--remove-cc', type=string_list, dest='cc-remove',
            help='remove emails from the CC list')
        person.add_argument(
            '--qa-contact',
            help='change the QA contact for this bug')
        status = self.parser.add_argument_group('Status related')
        status.add_argument(
            '-d', '--duplicate', type=int,
            metavar='BUG_ID', dest='dupe_of',
            help='mark bug as a duplicate')
        status.add_argument(
            '--fixed', action='store_true',
            help='mark bug as RESOLVED, FIXED')
        status.add_argument(
            '--invalid', action='store_true',
            help='mark bug as RESOLVED, INVALID')
        time = self.parser.add_argument_group('Time related')
        time.add_argument(
            '--deadline',
            help='change the deadline for this bug')
        time.add_argument(
            '--estimated-time', metavar='TIME',
            help='change the estimated time for this bug')
        time.add_argument(
            '--remaining-time', metavar='TIME',
            help='change the remaining time for this bug')
        time.add_argument(
            '--work-time', metavar='TIME',
            help='set number of hours worked on this bug as part of this change'),


@args.subcmd(BugzillaOpts)
class Search(args.Search):

    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        # optional args
        self.opts.add_argument(
            '--output',
            help='custom format for search output')
        person = self.parser.add_argument_group('Person related')
        person.add_argument(
            '-a', '--assigned-to', type=string_list, action=parse_stdin,
            help='email of the person the bug is assigned to')
        person.add_argument(
            '-r', '--creator', type=string_list, action=parse_stdin,
            help='email of the person who created the bug')
        # XXX: undocumented in the Bugzilla Webservice API
        # only works with >= bugzilla-5
        person.add_argument(
            '--cc', type=string_list, action=parse_stdin,
            help='email in the CC list for the bug')
        # XXX: undocumented in the Bugzilla Webservice API, uses advanced search URL params
        # only works with >= bugzilla-5
        person.add_argument(
            '--commenter', type=string_list, action=parse_stdin,
            help='commenter in the bug')
        person.add_argument(
            '--qa-contact',
            help='email of the QA contact for the bug')
        time = self.parser.add_argument_group('Time related')
        time.add_argument(
            '-c', '--created', type=date,
            dest='creation_time', metavar='TIME',
            action=partial(parse_stdin, date),
            help='bugs created at this time or later')
        time.add_argument(
            '-m', '--modified', type=date,
            dest='last_change_time', metavar='TIME',
            action=partial(parse_stdin, date),
            help='bugs modified at this time or later')
        attr = self.parser.add_argument_group('Attribute related')
        attr.add_argument(
            '-s', '--status', type=string_list,
            action=parse_stdin,
            help='restrict by status (one or more)')
        attr.add_argument(
            '-v', '--version', type=string_list,
            action=parse_stdin,
            help='restrict by version (one or more)')
        attr.add_argument(
            '-w', '--whiteboard', type=string_list,
            action=parse_stdin,
            help='status whiteboard')
        attr.add_argument(
            '-C', '--component', type=string_list,
            action=parse_stdin,
            help='restrict by component (one or more)')
        # XXX: undocumented in the Bugzilla Webservice API
        # only works with >= bugzilla-5
        attr.add_argument(
            '-K', '--keywords', type=string_list,
            action=parse_stdin,
            help='restrict by keywords (one or more)')
        # XXX: undocumented in the Bugzilla Webservice API
        # only works with >= bugzilla-5
        attr.add_argument(
            '--blocks', type=id_list,
            action=partial(parse_stdin, ids),
            help='restrict by bug blocks')
        # XXX: undocumented in the Bugzilla Webservice API
        # only works with >= bugzilla-5
        attr.add_argument(
            '--depends', type=id_list, dest='depends_on',
            action=partial(parse_stdin, ids),
            help='restrict by bug depends')
        # XXX: used to be documented in the Bugzilla 3.6 Webservice API, but is now undocumented
        # assumes Bugzilla instance uses votes, otherwise returns odd results
        attr.add_argument(
            '--votes',
            help='restrict bugs by the specified number of votes or greater')
        attr.add_argument(
            '--alias', type=string_list,
            action=parse_stdin,
            help='unique alias for this bug')
        attr.add_argument(
            '--id', type=id_list,
            action=partial(parse_stdin, ids),
            help='restrict by bug ID(s)')
        attr.add_argument(
            '--op-sys', type=string_list,
            action=parse_stdin,
            help='restrict by operating system (one or more)')
        attr.add_argument(
            '--platform', type=string_list,
            action=parse_stdin,
            help='restrict by platform (one or more)')
        attr.add_argument(
            '--priority', type=string_list,
            action=parse_stdin,
            help='restrict by priority (one or more)')
        attr.add_argument(
            '--product', type=string_list,
            action=parse_stdin,
            help='restrict by product (one or more)')
        attr.add_argument(
            '--resolution', type=string_list,
            action=parse_stdin,
            help='restrict by resolution')
        attr.add_argument(
            '--severity', type=string_list,
            action=parse_stdin,
            help='restrict by severity (one or more)')
        attr.add_argument(
            '--target-milestone', type=string_list,
            action=parse_stdin,
            help='restrict by target milestone (one or more)')
        attr.add_argument(
            '--url', type=string_list,
            action=parse_stdin,
            help='restrict by url (one or more)')


@args.subcmd(BugzillaOpts)
class Changes(args.ReceiveSubcmd):

    def __init__(self, *args, **kw):
        super().__init__(*args, desc='get changes from bug(s)', **kw)
        # positional args
        self.parser.add_argument(
            'ids', metavar='ID',
            type=id_list,
            action=partial(parse_stdin, ids),
            help='ID(s) or alias(es) of the bug(s) to retrieve all changes')

        # optional args
        self.opts.add_argument(
            '-c', '--created', dest='creation_time',
            metavar='TIME', type=date,
            action=partial(parse_stdin, date),
            help='changes made at this time or later')
        self.opts.add_argument(
            '-m', '--match', type=string_list,
            help='restrict by matching changed fields')
        self.opts.add_argument(
            '-n', '--number',
            dest='change_num', type=id_list,
            action=partial(parse_stdin, ids),
            help='restrict by change number(s)')
        self.opts.add_argument(
            '--output',
            help='custom format for output')
        self.opts.add_argument(
            '-r', '--creator',
            type=string_list, action=parse_stdin,
            help='restrict by person who made the change')


@args.subcmd(BugzillaOpts)
class Comments(args.ReceiveSubcmd):

    def __init__(self, *args, **kw):
        super().__init__(*args, desc='get comments from bug(s)', **kw)
        # positional args
        self.parser.add_argument(
            'ids', metavar='ID',
            type=id_list,
            action=partial(parse_stdin, ids),
            help='ID(s) or alias(es) of the bug(s) to retrieve all comments')

        # optional args
        self.opts.add_argument(
            '-n', '--number', dest='comment_num', type=id_list,
            action=partial(parse_stdin, ids),
            help='restrict by comment number(s)')
        self.opts.add_argument(
            '--output',
            help='custom format for output')
        self.opts.add_argument(
            '-c', '--created', dest='creation_time',
            metavar='TIME', type=date,
            help='comments made at this time or later')
        self.opts.add_argument(
            '-r', '--creator', type=string_list, action=parse_stdin,
            help='restrict by the email of the person who made the comment')
        self.opts.add_argument(
            '-a', '--attachment', action='store_true',
            help='restrict by comments that include attachments')


@args.subcmd(BugzillaOpts)
class Version(args.Subcmd):

    def __init__(self, *args, **kw):
        super().__init__(*args, desc='get bugzilla version', **kw)


@args.subcmd(BugzillaOpts)
class Extensions(args.Subcmd):

    def __init__(self, *args, **kw):
        super().__init__(*args, desc='get bugzilla extensions', **kw)


@args.subcmd(BugzillaOpts)
class Products(args.Subcmd):

    def __init__(self, *args, **kw):
        super().__init__(*args, desc='get bugzilla products', **kw)
        # positional args
        self.parser.add_argument(
            'products', nargs='?',
            type=string_list, action=parse_stdin,
            help='either ID or name')


@args.subcmd(BugzillaOpts)
class Users(args.Subcmd):

    def __init__(self, *args, **kw):
        super().__init__(*args, desc='get bugzilla users', **kw)
        # positional args
        self.parser.add_argument(
            'users', nargs='+', action=parse_stdin,
            help='either ID, login, or matching string')


@args.subcmd(BugzillaOpts)
class Fields(args.Subcmd):

    def __init__(self, *args, **kw):
        super().__init__(*args, desc='get bugzilla fields', **kw)
        # positional args
        self.parser.add_argument(
            'fields', nargs='?',
            type=string_list, action=parse_stdin,
            help='either ID or name')
