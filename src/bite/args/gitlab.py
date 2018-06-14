from functools import partial

from .. import args
from ..argparser import ParseStdin


class GitlabOpts(args.ServiceOpts):
    """Gitlab options."""

    _service = 'gitlab'


class Search(args.PagedSearch, GitlabOpts):

    def add_args(self):
        super().add_args()
        time = self.parser.add_argument_group('Time related')
        time.add_argument(
            '-c', '--created', type='time interval', metavar='TIME_INTERVAL',
            help=f'{self.service.item.type}s created within a specified time interval')
        time.add_argument(
            '-m', '--modified', type='time interval', metavar='TIME_INTERVAL',
            help=f'{self.service.item.type}s modified within a specified time interval')

        attr = self.parser.add_argument_group('Attribute related')
        attr.add_argument(
            '--id', type='id_list', action=partial(ParseStdin, 'ids'),
            help=f'restrict by {self.service.item.type} ID(s)')
        attr.add_argument(
            '--labels', type='str_list', action='parse_stdin',
            help=f'restrict by {self.service.item.type} labels')
        attr.add_argument(
            '-s', '--status',
            help='restrict by status')
