from functools import partial

from .. import args
from ..argparser import ParseStdin


class GitlabOpts(args.ServiceOpts):
    """Gitlab"""

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
            '--milestone',
            help='restrict by milestone')
        attr.add_argument(
            '-s', '--status',
            help='restrict by status')

        if self.service.group is None:
            attr.add_argument(
                '--group',
                help='restrict by repos owned by a given group')
            attr.add_argument(
                '--repo',
                help='restrict by a given repo')
        elif self.service.repo is None:
            attr.add_argument(
                '--project',
                help='restrict by a given project')


class Project(args.Subcmd, GitlabOpts):

    _name = 'project'

    @property
    def description(self):
        return 'operate on projects'

    @staticmethod
    def add(service):
        """Only define the subcommand for non-repo specific connections."""
        return service.repo is None


class ProjectSearch(args.Search, GitlabOpts):

    _name = 'project search'

    @property
    def description(self):
        return 'search for projects'

    @staticmethod
    def add(service):
        """Only define the subcommand for non-repo specific connections."""
        return service.repo is None
