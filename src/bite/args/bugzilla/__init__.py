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


class Bugzilla4_4_Opts(args.ServiceOpts):
    """Bugzilla 4.4 options."""

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


class Bugzilla5_0_Opts(Bugzilla4_4_Opts):
    """Bugzilla 5.0 options."""


class Bugzilla5_2_Opts(Bugzilla5_0_Opts):
    """Bugzilla 5.2 options."""


@args.subcmd(Bugzilla4_4_Opts)
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


@args.subcmd(Bugzilla4_4_Opts)
class Attachments(args.Attachments):

    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        # optional args
        self.opts.add_argument(
            '-l', '--list', action='store_true', dest='show_metadata',
            help='list attachment metadata')


@args.subcmd(Bugzilla4_4_Opts)
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


@args.subcmd(Bugzilla4_4_Opts)
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


@args.subcmd(Bugzilla4_4_Opts)
class Modify(args.Modify):

    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        # optional args
        attr = self.parser.add_argument_group('Attribute related')
        attr.add_argument(
            '-c', '--comment', metavar='COMMENT', dest='comment-body',
            help='add comment from command line')
        attr.add_argument(
            '-S', '--severity',
            help='set severity for this bug')
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
            '--alias', action='csv_elements',
            help='add/remove/set aliases',
            docs="""
                Add, remove, or set bug aliases.

                Use comma-separated values to add, remove, or set aliases for a
                given bug. Use the prefixes '+' and '-' for each value to add
                and remove aliases, respectively. In order to set aliases for a
                bug, don't use any prefixes for the passed values.

                Note that setting aliases overrides the current aliases for the
                bug as well as any passed add/remove values.

                In addition, this action can only be performed on a single bug
                at a time so passing multiple bug ID targets will cause an
                error.
            """)
        attr.add_argument(
            '--blocks', action='csv_elements', metavar='BUG_ID',
            help='add/remove/set blockers',
            docs="""
                Add, remove, or set bug blockers.

                Use comma-separated bug IDS to add, remove, or set blockers for a
                given bug. Use the prefixes '+' and '-' for each ID to add
                and remove blockers, respectively. In order to set blockers for a
                bug, don't use any prefixes for the passed IDs.

                Note that setting blockers overrides the current blockers for the
                bug as well as any passed add/remove values.
            """)
        attr.add_argument(
            '--component',
            help='change the component for this bug')
        attr.add_argument(
            '--depends', action='csv_elements', metavar='BUG_ID',
            help='add/remove/set dependencies',
            docs="""
                Add, remove, or set bug dependencies.

                Use comma-separated bug IDS to add, remove, or set dependencies
                for a given bug. Use the prefixes '+' and '-' for each ID to
                add and remove dependencies, respectively. In order to set
                dependencies for a bug, don't use any prefixes for the passed
                IDs.

                Note that setting dependencies overrides the current
                dependencies for the bug as well as any passed add/remove
                values.
            """)
        attr.add_argument(
            '--groups', action='csv_negations', metavar='GROUP',
            help='add/remove groups',
            docs="""
                Add or remove bug groups.

                Use comma-separated values to add or remove groups for a given
                bug. Use the prefixes '+' and '-' for each ID to add and remove
                groups, respectively.
            """)
        attr.add_argument(
            '-K', '--keywords', action='csv_elements', metavar='KEYWORDS',
            help='add/remove/set keywords',
            docs="""
                Add, remove, or set bug keywords.

                Use comma-separated values to add, remove, or set keywords for
                a given bug. Use the prefixes '+' and '-' for each value to add
                and remove keywords, respectively. In order to set keywords for
                a bug, don't use any prefixes for the passed values.

                Note that setting keywords overrides the current keywords for
                the bug as well as any passed add/remove values.
            """)
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
            '--see-also', action='csv_negations', metavar='URL',
            help='add/remove "see also" URLs',
            docs="""
                Add or remove "See Also" URLs.

                Use comma-separated values to add or remove URLs for a given
                bug. Use the prefixes '+' and '-' for each value to add and
                remove entries, respectively.
            """)
        person = self.parser.add_argument_group('Person related')
        person.add_argument(
            '-a', '--assigned-to',
            help='change assignee for this bug')
        person.add_argument(
            '--cc', action='csv_negations',
            help='add/remove CCs',
            docs="""
                Add or remove users from the CC list.

                Use comma-separated values to add or remove CCs for a given
                bug. Use the prefixes '+' and '-' for each user to add and
                remove entries, respectively.
            """)
        person.add_argument(
            '--qa-contact',
            help='change the QA contact for this bug')
        status = self.parser.add_argument_group('Status related')
        status.add_argument(
            '-s', '--status',
            help='set new status of bug (e.g. RESOLVED)')
        status.add_argument(
            '-R', '--resolution',
            help='set new resolution')
        status.add_argument(
            '-d', '--duplicate', type=int,
            metavar='BUG_ID', dest='dupe_of',
            help='mark bug as a duplicate')
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


@args.subcmd(Bugzilla4_4_Opts)
class Search(args.PagedSearch):

    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        # optional args
        self.opts.add_argument(
            '--output',
            help='custom format for search output')
        self.person = self.parser.add_argument_group('Person related')
        self.person.add_argument(
            '-a', '--assigned-to', type=string_list, action=parse_stdin,
            help='email of the person the bug is assigned to')
        self.person.add_argument(
            '-r', '--creator', type=string_list, action=parse_stdin,
            help='email of the person who created the bug')
        self.person.add_argument(
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
        self.attr = self.parser.add_argument_group('Attribute related')
        self.attr.add_argument(
            '-s', '--status', type=string_list,
            action=parse_stdin,
            help='restrict by status (one or more)')
        self.attr.add_argument(
            '-v', '--version', type=string_list,
            action=parse_stdin,
            help='restrict by version (one or more)')
        self.attr.add_argument(
            '-w', '--whiteboard', type=string_list,
            action=parse_stdin,
            help='status whiteboard')
        self.attr.add_argument(
            '-C', '--component', type=string_list,
            action=parse_stdin,
            help='restrict by component (one or more)')
        self.attr.add_argument(
            '--alias', type=string_list,
            action=parse_stdin,
            help='unique alias for this bug')
        self.attr.add_argument(
            '--id', type=id_list,
            action=partial(parse_stdin, ids),
            help='restrict by bug ID(s)')
        self.attr.add_argument(
            '--op-sys', type=string_list,
            action=parse_stdin,
            help='restrict by operating system (one or more)')
        self.attr.add_argument(
            '--platform', type=string_list,
            action=parse_stdin,
            help='restrict by platform (one or more)')
        self.attr.add_argument(
            '--priority', type=string_list,
            action=parse_stdin,
            help='restrict by priority (one or more)')
        self.attr.add_argument(
            '--product', type=string_list,
            action=parse_stdin,
            help='restrict by product (one or more)')
        self.attr.add_argument(
            '--resolution', type=string_list,
            action=parse_stdin,
            help='restrict by resolution')
        self.attr.add_argument(
            '--severity', type=string_list,
            action=parse_stdin,
            help='restrict by severity (one or more)')
        self.attr.add_argument(
            '--target-milestone', type=string_list,
            action=parse_stdin,
            help='restrict by target milestone (one or more)')
        self.attr.add_argument(
            '--url', type=string_list,
            action=parse_stdin,
            help='restrict by url (one or more)')


@args.subcmd(Bugzilla5_0_Opts, 'search')
class Search5_0(Search):

    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        self.opts.add_argument(
            '--sort', action='csv', metavar='TERM',
            help='sorting order for search query',
            docs="""
                Requested sorting order for the given search query.

                Providing multiple sorting terms will give a data response
                sorted by the first term, then the second, and so on.

                Sorting in descending order can be done by prefixing a given
                sorting term with '-'; otherwise, sorting is done in an
                ascending fashion by default.

                Note that if an invalid sorting request is made, bugzilla will
                fall back to its default which is sorting by bug ID. Also, some
                sorting methods such as last-visited require an authenticated
                session to work properly.
            """)
        self.opts.add_argument(
            '-q', '--quicksearch',
            help='search for bugs using quicksearch syntax',
            docs="""
                Search for bugs using quicksearch syntax.

                See https://bugzilla.mozilla.org/page.cgi?id=quicksearch.html
                and http://www.squarefree.com/bugzilla/quicksearch-help.html
                for a description of the syntax and various examples.
            """)
        self.opts.add_argument(
            '--advanced-url', metavar='URL',
            help='search for bugs using an advanced search URL',
            docs="""
                Search for bugs using URLs from the web UI's advanced search.

                Using this, one can construct any custom search by the advanced
                search interface in the regular web UI and then use the
                resulting URL to peform the same query on the command line.

                Note that options specified on the command line will override
                any matching URL parameters.
            """)
        self.opts.add_argument(
            '-S', '--saved-search',
            help='search for bugs using a saved search')
        self.person.add_argument(
            '--cc', type=string_list, action=parse_stdin,
            help='email in the CC list for the bug')
        self.person.add_argument(
            '--commenter', type=string_list, action=parse_stdin,
            help='commenter in the bug')
        self.attr.add_argument(
            '-K', '--keywords', type=string_list,
            action=parse_stdin,
            help='restrict by keywords (one or more)')
        self.attr.add_argument(
            '--blocks', type=id_list,
            action=partial(parse_stdin, ids),
            help='restrict by bug blocks')
        self.attr.add_argument(
            '--depends', type=id_list, dest='depends_on',
            action=partial(parse_stdin, ids),
            help='restrict by bug depends')
        self.attr.add_argument(
            '--votes',
            help='restrict bugs by the specified number of votes or greater')
        self.attr.add_argument(
            '--comments', type=int,
            help='restrict bugs by the specified number of comments or greater')


@args.subcmd(Bugzilla5_0_Opts)
class APIKeys(args.Subcmd):
    """Interface to working with bugzilla apikeys."""

    def __init__(self, *args, **kw):
        super().__init__(*args, desc='generate, revoke, or list API keys', **kw)
        single_action = self.parser.add_mutually_exclusive_group()
        single_action.add_argument(
            '-l', '--list', action='store_true',
            help='list available apikeys')
        single_action.add_argument(
            '-g', '--generate', nargs='?', const='bite', metavar='DESCRIPTION',
            help='generate an apikey')
        single_action.add_argument(
            '-r', '--revoke', action='csv_negations', metavar='KEY',
            help='toggle apikey(s) revoked status',
            docs="""
                Add/remove apikeys from the revoked list using their
                descriptions or values.

                To revoke multiple keys at once, use a comma-separated list.
                Also, prefix an argument with '-' to unrevoke the related key.
            """)


@args.subcmd(Bugzilla5_0_Opts)
class SavedSearches(args.Subcmd):
    """Interface to working with bugzilla saved searches."""

    def __init__(self, *args, **kw):
        super().__init__(*args, desc='save, remove, or list saved searches', **kw)
        single_action = self.parser.add_mutually_exclusive_group()
        single_action.add_argument(
            '-l', '--list', action='store_true',
            help='list available saved searches')
        single_action.add_argument(
            '-s', '--save', nargs=2, metavar='NAME URL',
            help='create a saved search')
        single_action.add_argument(
            '-r', '--remove', action='csv', metavar='NAME',
            help='remove saved search(es)')


@args.subcmd(Bugzilla4_4_Opts)
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


@args.subcmd(Bugzilla4_4_Opts)
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


@args.subcmd(Bugzilla4_4_Opts)
class Version(args.Subcmd):

    def __init__(self, *args, **kw):
        super().__init__(*args, desc='get bugzilla version', **kw)


@args.subcmd(Bugzilla4_4_Opts)
class Extensions(args.Subcmd):

    def __init__(self, *args, **kw):
        super().__init__(*args, desc='get bugzilla extensions', **kw)


@args.subcmd(Bugzilla4_4_Opts)
class Products(args.Subcmd):

    def __init__(self, *args, **kw):
        super().__init__(*args, desc='get bugzilla products', **kw)
        # positional args
        self.parser.add_argument(
            'products', nargs='?',
            type=string_list, action=parse_stdin,
            help='either ID or name')


@args.subcmd(Bugzilla4_4_Opts)
class Users(args.Subcmd):

    def __init__(self, *args, **kw):
        super().__init__(*args, desc='get bugzilla users', **kw)
        # positional args
        self.parser.add_argument(
            'users', nargs='+', action=parse_stdin,
            help='either ID, login, or matching string')


@args.subcmd(Bugzilla4_4_Opts)
class Fields(args.Subcmd):

    def __init__(self, *args, **kw):
        super().__init__(*args, desc='get bugzilla fields', **kw)
        # positional args
        self.parser.add_argument(
            'fields', nargs='?',
            type=string_list, action=parse_stdin,
            help='either ID or name')
