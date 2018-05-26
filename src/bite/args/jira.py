from functools import partial

from .. import args
from ..argparser import ParseStdin


class JiraOpts(args.ServiceOpts):
    """Jira options."""

    _service = 'jira'


@args.subcmd(JiraOpts)
class Search(args.PagedSearch):

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
        self.attr.add_argument(
            '--id', type='id_list',
            action=partial(ParseStdin, 'ids'),
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
