from functools import partial

from .. import args
from ..argparser import parse_stdin, id_list, ids, string_list


class RoundupOpts(args.ServiceOpts):

    _service = 'roundup'


@args.subcmd(RoundupOpts)
class Get(args.Get):

    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        # positional args
        self.parser.add_argument(
            'ids', type=id_list, metavar='ID',
            action=partial(parse_stdin, ids),
            help='ID(s) or alias(es) of the issue(s) to retrieve')


@args.subcmd(RoundupOpts)
class Attachments(args.Attachments):

    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        # positional args
        self.parser.add_argument('ids',
            type=id_list,
            action=partial(parse_stdin, ids),
            metavar='ID',
            help='attachment ID(s) (or issue ID(s) when --item-id is used)')


# def subcmds(subparsers):
#     # create arguments
#     parser = subparsers.add_parser('create',
#         description='create a new issue',
#         help='create a new issue')
#     parser.set_defaults(fcn='create')
#     # optional args
#     person = parser.add_argument_group('Person related')
#     person.add_argument('-a', '--assigned-to',
#         dest='assignedto',
#         metavar='ASSIGNED_TO',
#         help='assign issue to someone other than the default assignee')
#     person.add_argument('--nosy',
#         type=string_list,
#         help='add a list of people who may be interested in the issue')
#     attr = parser.add_argument_group('Attribute related')
#     attr.add_argument('-t', '--title',
#         help='title of issue')
#     attr.add_argument('-s', '--status',
#         help='status of issue')
#     attr.add_argument('-K', '--keywords',
#         type=string_list,
#         help='set the keywords of this issue')
#     attr.add_argument('--priority',
#         help='set priority for the issue')
#
#     # modify arguments
#     parser = subparsers.add_parser(
#         'modify', verbose=False,
#         description='modify issues(s)',
#         help='modify issues(s)')
#     parser.set_defaults(fcn='modify')
#     # positional args
#     parser.add_argument('ids',
#         type=id_list,
#         action=partial(parse_stdin, ids),
#         metavar='ID',
#         help='ID(s) of the issue(s) to modify')
#     # optional args
#     attr = parser.add_argument_group('Attribute related')
#     attr.add_argument('-t', '--title',
#         help='set title of issue')
#
#     # search arguments
#     parser = subparsers.add_parser(
#         'search', verbose=False,
#         description='search for issues',
#         help='search for issues')
#     parser.set_defaults(fcn='search')
#     # positional args
#     parser.add_argument('terms',
#         action=parse_stdin,
#         nargs='*',
#         help='strings to search for in title and/or body')
#     # optional args
#     attr = parser.add_argument_group('Attribute related')
#     attr.add_argument('-s', '--status',
#         help='restrict by status')
