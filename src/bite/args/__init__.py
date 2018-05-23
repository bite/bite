import argparse
from functools import partial

from snakeoil.cli import arghparse
from snakeoil.demandload import demandload

from ..exceptions import BiteError
from ..argparser import (
    ParseStdin, Comment, IDList, StringList, IDs, ID_Maps, ID_Str_Maps,
    Date, TimeIntervalArg,
)
from ..utils import str2bool, block_edit, confirm

demandload('bite:const')


def subcmd(service_cls, name=None):
    """Register service subcommands."""
    def wrapped(cls, *args, **kwds):
        subcmd_name = name if name is not None else cls.__name__.lower()
        # add subcommand to its related service class
        setattr(service_cls, subcmd_name, cls)
        # store the subcommand name inside its class for consistent help output
        setattr(cls, '_subcmd_name', subcmd_name)
        return cls
    return wrapped


class Subcmd(object):

    def __init__(self, parser, service, name=None):
        name = name if name is not None else getattr(self, '_subcmd_name')
        self.service = service
        if self.description is None:
            raise ValueError(
                f'missing description for subcommand {name!r}: {self.__class__}')

        # Suppress empty attribute creation during parse_args() calls, this
        # means that only the args passed in will create attributes in the
        # returned namespace instead of attributes for all options using their
        # default values.
        subcmd_parser = partial(
            arghparse.ArgumentParser, argument_default=argparse.SUPPRESS)

        self.parser = parser.add_parser(
            name, cls=subcmd_parser, quiet=False, color=False, description=self.description)

        # register arg types and actions for subcmd parsing
        self.parser.register('type', 'ids', IDs(service))
        self.parser.register('type', 'id_list', IDList(service))
        self.parser.register('type', 'id_maps', ID_Maps(service))
        self.parser.register('type', 'id_str_maps', ID_Str_Maps(service))
        self.parser.register('type', 'str_list', StringList(service))
        self.parser.register('type', 'comment', Comment(service))
        self.parser.register('type', 'date', Date(service))
        self.parser.register('type', 'time_interval', TimeIntervalArg(service))
        self.parser.register('action', 'parse_stdin', ParseStdin)

        self.parser.set_defaults(fcn=name)
        self.opts = self.parser.add_argument_group(f'{name.capitalize()} options')
        self.add_args()

    @property
    def description(self):
        return self.__doc__

    def add_args(self):
        """Add arguments to the subcommand parser."""

    def finalize_args(self, args):
        """Check and finalize arguments passed to the subcommand parser."""
        return args


class ServiceOpts(object):

    _service = None

    def __init__(self, parser, service_name):
        self.parser = parser
        # flag to re-parse unparsed args for service specific options
        self._reparse = False

        # type conversion mapping for config opts
        self.config_map = {
            'skip_auth': str2bool,
            'verify': str2bool,
            'quiet': str2bool,
            'columns': lambda x: setattr(const, 'COLUMNS', int(x)),
            'concurrent': int,
            'timeout': int,
            'max_results': int,
        }

        from ..scripts.bite import service_specific_opts
        self.service_opts = service_specific_opts
        self.service_opts.title = f"{service_name.split('-')[0].capitalize()} specific options"

        try:
            self.main_opts()
            self._reparse = True
        except argparse.ArgumentError as e:
            # skip multiple main_opts() run issues during doc generation
            if 'conflicting option string' not in str(e):
                raise
        except NotImplementedError:
            pass

    def subcmds(self):
        """Get sequence of subcommands defined for the service."""
        l = []
        for x in dir(self):
            attr = getattr(self, x)
            if isinstance(attr, type) and issubclass(attr, Subcmd):
                l.append((x, attr))
        return tuple(l)

    def main_opts(self):
        """Add service specific top-level options."""
        raise NotImplementedError

    def add_config_opts(self, args, config_opts):
        """Add service specific config options."""
        try:
            # merge config options, command line options override these
            for k, v in config_opts.items():
                if getattr(args, k, None) is None:
                    setattr(args, k, self.config_map.get(k, str)(v))
        except ValueError as e:
            raise BiteError(f'invalid config value for {k!r}: {v!r}')

    def add_subcmd_opts(self, service, subcmd):
        """Add subcommand specific options."""
        subcmd_parser = self.parser.add_subparsers(help='help for subcommands')
        # try to only add the options for the single subcmd
        try:
            cls = getattr(self, subcmd)
            return cls(parser=subcmd_parser, service=service, name=subcmd)
        # fallback to adding all subcmd options, since the user is
        # requesting help output (-h/--help) or entering unknown input
        except AttributeError:
            for subcmd, cls in self.subcmds():
                cls(parser=subcmd_parser, service=service)


class RequestSubcmd(Subcmd):

    def add_args(self):
        super().add_args()
        self.opts.add_argument(
            '--dry-run', action='store_true',
            help='do everything except requesting or sending data')


class SendSubcmd(RequestSubcmd):

    def add_args(self):
        super().add_args()
        self.opts.add_argument(
            '--ask', action='store_true',
            help='require confirmation before submitting modifications')


class ReceiveSubcmd(RequestSubcmd):

    def add_args(self):
        super().add_args()
        self.opts.add_argument(
            '-f', '--fields', type='str_list',
            metavar='FIELD | FIELD,FIELD,...',
            help='fields to output')


class Search(ReceiveSubcmd):

    @property
    def description(self):
        return f"search for {self.service.item.type}s"

    def add_args(self):
        super().add_args()
        # positional args
        self.parser.add_argument(
            'terms', nargs='*', metavar='TERM', action='parse_stdin',
            help=f"string(s) to search for in {self.service.item.type} summary/title")


class PagedSearch(Search):

    def add_args(self):
        super().add_args()
        # optional args
        self.opts.add_argument(
            '--limit', type=int,
            help='limit the number of records returned in a search')
        self.opts.add_argument(
            '--offset', type=int,
            help='set the start position for a search')


class Get(ReceiveSubcmd):

    @property
    def description(self):
        return f"get {self.service.item.type}(s)"

    def add_args(self, history=False):
        super().add_args()
        # positional args
        self.parser.add_argument(
            'ids', type='ids', nargs='+', metavar='ID', action='parse_stdin',
            help=f"ID(s) or alias(es) of the {self.service.item.type}(s) to retrieve")

        # optional args
        if self.service.item_endpoint is not None:
            single_action = self.opts.add_mutually_exclusive_group()
            single_action.add_argument(
                '-B', '--browser', action='store_true',
                help=f'open {self.service.item.type} URL(s) in a browser')
            single_action.add_argument(
                '-U', '--url', dest='output_url', action='store_true',
                help=f'output {self.service.item.type} URL(s)')
        self.opts.add_argument(
            '-A', '--no-attachments', action='store_false', dest='get_attachments',
            help='do not show attachments')
        self.opts.add_argument(
            '-C', '--no-comments', action='store_false', dest='get_comments',
            help='do not show comments')
        if history:
            self.opts.add_argument(
                '-H', '--show-history', action='store_true', dest='get_changes',
                help=f'show {self.service.item.type} history')


class Attachments(Subcmd):

    @property
    def description(self):
        return f"get attachments from {self.service.item.type}(s)"

    def add_args(self, id_map=None, item_id=True):
        super().add_args()
        # positional args
        if id_map:
            self.parser.add_argument(
                'ids', type=id_map, nargs='+', metavar='ID[:A_ID[,...]]', action='parse_stdin',
                help=f"{self.service.item.type} ID(s) or {self.service.item.type} ID to attachment ID map(s)")
            self.parser.set_defaults(id_map=True)
        else:
            self.parser.add_argument(
                'ids', type='ids', nargs='+', metavar='ID', action='parse_stdin',
                help=f"attachment ID(s) (or {self.service.item.type} ID(s) when --item-id is used)")

        # optional args
        single_action = self.opts.add_mutually_exclusive_group()
        if self.service.attachment_endpoint is not None:
            single_action.add_argument(
                '-B', '--browser', action='store_true',
                help="open attachment URL(s) in a browser")
            single_action.add_argument(
                '-U', '--url', dest='output_url', action='store_true',
                help='output attachment URL(s)')
        single_action.add_argument(
            '-V', '--view', action='store_true', dest='view_attachment',
            help='output attachment data')
        if item_id:
            self.opts.add_argument(
                '-I', '--item-id', action='store_true',
                help='search by item ID(s) rather than attachment ID(s)')
        self.opts.add_argument(
            '--save-to',
            help='save attachment(s) into a specified dir')


class Changes(ReceiveSubcmd):

    @property
    def description(self):
        return f"get changes from {self.service.item.type}(s)"

    def add_args(self):
        super().add_args()
        # positional args
        self.parser.add_argument(
            'ids', type='ids', nargs='+', metavar='ID', action='parse_stdin',
            help=f"ID(s) or alias(es) of the {self.service.item.type}(s) "
                 "to retrieve all changes")
        # optional args
        self.opts.add_argument(
            '-n', '--number',
            dest='change_num', type='id_list',
            action=partial(ParseStdin, 'ids'),
            help='restrict by change number(s)')
        self.opts.add_argument(
            '-r', '--creator',
            type='str_list', action='parse_stdin',
            help='restrict by person who made the change')


class Comments(ReceiveSubcmd):

    @property
    def description(self):
        return f"get comments from {self.service.item.type}(s)"

    def add_args(self):
        super().add_args()
        # positional args
        self.parser.add_argument(
            'ids', type='ids', nargs='+', metavar='ID', action='parse_stdin',
            help=f"ID(s) or alias(es) of the {self.service.item.type}(s) "
                 "to retrieve all comments")
        # optional args
        self.opts.add_argument(
            '-n', '--number', dest='comment_num', type='id_list',
            action=partial(ParseStdin, 'ids'),
            help='restrict by comment number(s)')
        self.opts.add_argument(
            '-r', '--creator', type='str_list', action='parse_stdin',
            help='restrict by the email of the person who made the comment')


class Attach(SendSubcmd):

    @property
    def description(self):
        return f"attach file to {self.service.item.type}(s)"

    def add_args(self):
        super().add_args()
        self.opts.add_argument(
            '-d', '--description',
            help='a long description of the attachment',
            dest='comment')
        self.opts.add_argument(
            '-t', '--title', dest='summary',
            help='a short description of the attachment (default: filename)')


class Modify(SendSubcmd):

    @property
    def description(self):
        return f"modify {self.service.item.type}(s)"

    def add_args(self):
        super().add_args()
        # positional args
        self.parser.add_argument(
            'ids', type='ids', nargs='+', metavar='ID', action='parse_stdin',
            help=f"ID(s) of the {self.service.item.type}(s) to modify")

        # optional args
        self.attr = self.parser.add_argument_group('Attribute related')
        single_action = self.attr.add_mutually_exclusive_group()
        single_action.add_argument(
            '-c', '--comment', nargs='?', const='__BITE_EDITOR__',
            type='comment', action='parse_stdin',
            help='add a comment')
        single_action.add_argument(
            '-r', '--reply', type='ids', nargs='+', dest='reply_ids',
            help='reply to a specific comment')

    def get_comment_reply(self, reply_ids, args):
        """Support reply to specific comment(s)."""
        item_id = args['ids'][0]
        try:
            comments = next(self.service.CommentsRequest(ids=[item_id]).send())
        except BiteError as e:
            self.parser.error(f'argument -r/--reply: {e}')

        # pull comment data in reply format
        initial_text = []
        try:
            for i in reply_ids:
                initial_text.append(comments[i].reply)
        except IndexError:
            self.parser.error(
                'argument -r/--reply: '
                f'nonexistent comment #{i} '
                f'({self.service.item.type} #{item_id} has {len(comments)} '
                'comments including the description)')
        initial_text = '\n\n'.join(initial_text)

        # request user changes
        while True:
            comment = block_edit(
                header=True, comment='Add reply to the requested comment(s)', comment_from=initial_text).strip()
            if (comment != initial_text or
                    confirm('No changes made to comment, submit anyway?')):
                break

        return comment

    def finalize_args(self, args):
        args = super().finalize_args(args)

        # support interactive comment replies
        reply_ids = args.pop('reply_ids', None)
        if reply_ids is not None:
            # replies force singular item ID input
            if len(args['ids']) > 1:
                self.parser.error(
                    '-r/--reply only works with singular '
                    f'{self.service.item.type} ID arguments')
            args['comment'] = self.get_comment_reply(reply_ids, args)

        return args


class Create(SendSubcmd):

    @property
    def description(self):
        return f"create a new {self.service.item.type}"

    def add_args(self):
        super().add_args()
        self.opts.add_argument(
            '-F', '--description-from',
            help='description from contents of file')
        self.opts.add_argument(
            '--append-command',
            help='append the output of a command to the description')
        self.opts.add_argument(
            '--batch', action='store_true',
            help='do not prompt for any values')
