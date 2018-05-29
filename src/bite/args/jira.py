from argparse import ArgumentTypeError
from functools import partial
import re

from .. import args
from ..argparser import ParseStdin, override_attr, ArgType


class JiraIDs(ArgType):
    """ID type for global Jira IDs."""

    @staticmethod
    def parse(s):
        if not re.match(r'[A-Z0-9]+-\d+', s):
            raise ArgumentTypeError(f'invalid item ID: {s!r}')
        return s

    def parse_stdin(self, data):
        return [self.parse(x) for x in data]


class JiraIDList(ArgType):

    @staticmethod
    def parse(s):
        l = []
        for item in s.split(','):
            l.append(JiraIDs.parse(item))
        return l


class JiraSubcmd(args.Subcmd):

    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        self.parser.register('type', 'jira_ids', JiraIDs(self.service))
        self.parser.register('type', 'jira_id_list', JiraIDList(self.service))


class JiraOpts(args.ServiceOpts):
    """Jira options."""

    _service = 'jira'

    def add_main_opts(self, service):
        if service.project is None:
            self.service_opts.add_argument(
                '--project', action=partial(override_attr, service, 'project'),
                help='define a specific project to target')


@args.subcmd(JiraOpts)
class Search(JiraSubcmd, args.PagedSearch):

    def add_args(self):
        super().add_args()

        self.person = self.parser.add_argument_group('Person related')
        self.person.add_argument(
            '-a', '--assigned-to', type='str_list', action='parse_stdin',
            help=f'user the {self.service.item.type} is assigned to')
        self.person.add_argument(
            '-r', '--creator', type='str_list', action='parse_stdin',
            help=f'user who created the {self.service.item.type}')
        self.person.add_argument(
            '--watchers', type='int range', metavar='LOWER[-UPPER]',
            help=f'{self.service.item.type} with a specified number of watchers')

        self.time = self.parser.add_argument_group('Time related')
        self.time.add_argument(
            '-c', '--created', type='time interval', metavar='TIME_INTERVAL',
            help=f'{self.service.item.type}s created within a specified time interval')
        self.time.add_argument(
            '-m', '--modified', type='time interval', metavar='TIME_INTERVAL',
            help=f'{self.service.item.type}s modified within a specified time interval')
        self.time.add_argument(
            '--resolved', type='time interval', metavar='TIME_INTERVAL',
            help=f'{self.service.item.type}s resolved within a specified time interval')
        self.time.add_argument(
            '--viewed', type='time interval', metavar='TIME_INTERVAL',
            help=f'{self.service.item.type}s viewed within a specified time interval')

        self.attr = self.parser.add_argument_group('Attribute related')
        if self.service.project is not None:
            self.attr.add_argument(
                '--id', type='id_list',
                action=partial(ParseStdin, 'ids'),
                help=f'restrict by {self.service.item.type} ID(s)')
        else:
            self.attr.add_argument(
                '--id', type='jira_id_list',
                action=partial(ParseStdin, 'jira_ids'),
                help=f'restrict by {self.service.item.type} ID(s)')
        self.attr.add_argument(
            '--attachments', nargs='?', type=int, const=1,
            help='restrict {self.service.item.type}s by attachment status',
            docs="""
                Search for {self.service.item.type}s by their attachment status.

                With no argument, this restricts {self.service.item.type}s
                returned to those that have attachments. If passed an argument
                of '0', returned {self.service.item.type}s will not have any
                attachments.
            """)
        self.attr.add_argument(
            '--votes', type='int range', metavar='LOWER[-UPPER]',
            help=f'{self.service.item.type}s with a specified number of votes')


@args.subcmd(JiraOpts)
class Get(JiraSubcmd, args.Get):

    def add_args(self):
        # Force "project-ID" based item IDs for conglomerate jira connections
        # that encompass all the projects available on the service.
        if self.service.project is None:
            # positional args
            self.parser.add_argument(
                'ids', type='jira_ids', nargs='+',
                metavar='PROJECT-ID', action=partial(ParseStdin, 'jira_ids'),
                help=f"ID(s) of the {self.service.item.type}(s) to retrieve")

        add_ids = self.service.project is not None
        super().add_args(ids=add_ids)


@args.subcmd(JiraOpts)
class Comments(args.Comments):
    pass


@args.subcmd(JiraOpts)
class Version(args.Subcmd):
    """get Jira version"""
