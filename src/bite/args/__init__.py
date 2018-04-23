from functools import partial

from snakeoil.demandload import demandload

from ..exceptions import BiteError
from ..argparser import parse_stdin, string_list, id_list, ids
from ..utils import str2bool

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

    def __init__(self, parser, service, name=None, desc=None):
        name = name if name is not None else getattr(self, '_subcmd_name')
        self.parser = parser.add_parser(
            name, quiet=False, color=False, description=desc)
        self.parser.set_defaults(fcn=name)
        self.opts = self.parser.add_argument_group(f'{name.capitalize()} options')


class ServiceOpts(object):

    _service = None

    def __init__(self, parser, service_name):
        self.parser = parser

        # type conversion mapping for config opts
        self.config_map = {
            'skip_auth': str2bool,
            'verify': str2bool,
            'quiet': str2bool,
            'columns': lambda x: setattr(const, 'COLUMNS', int(x)),
            'concurrent': int,
            'timeout': int,
        }

        from ..scripts.bite import service_specific_opts
        self.service_opts = service_specific_opts
        self.service_opts.title = service_name.split('-')[0].capitalize() + ' specific options'

        self.main_opts()

    def main_opts(self):
        """Add service specific top-level options."""

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
            cls(parser=subcmd_parser, service=service, name=subcmd)
        # fallback to adding all subcmd options, since the user is
        # requesting help output (-h/--help) or entering unknown input
        except AttributeError:
            for cls in (getattr(self, attr) for attr in dir(self)):
                if isinstance(cls, type) and issubclass(cls, Subcmd):
                    cls(parser=subcmd_parser, service=service)


class RequestSubcmd(Subcmd):

    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        self.opts.add_argument(
            '--dry-run', action='store_true',
            help='do everything except requesting or sending data')


class SendSubcmd(RequestSubcmd):

    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        self.opts.add_argument(
            '--ask', action='store_true',
            help='require confirmation before submitting modifications')


class ReceiveSubcmd(RequestSubcmd):

    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        self.opts.add_argument(
            '-f', '--fields', type=string_list,
            metavar='FIELD | FIELD,FIELD,...',
            help='fields to output')


class Search(ReceiveSubcmd):

    def __init__(self, *args, desc=None, **kw):
        if desc is None:
            desc = f"search for {kw['service'].item.type}s"
        super().__init__(*args, desc=desc, **kw)

        # positional args
        self.parser.add_argument(
            'terms', nargs='*', metavar='TERM', action=parse_stdin,
            help=f"string(s) to search for in {kw['service'].item.type} summary/title")


class PagedSearch(Search):

    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        # optional args
        self.opts.add_argument(
            '--limit', type=int,
            help='limit the number of records returned in a search')
        self.opts.add_argument(
            '--offset', type=int,
            help='set the start position for a search')


class Get(ReceiveSubcmd):

    def __init__(self, *args, desc=None, **kw):
        if desc is None:
            desc = f"get {kw['service'].item.type}(s)"
        super().__init__(*args, desc=desc, **kw)

        # positional args
        self.parser.add_argument(
            'ids', type=id_list, metavar='ID',
            action=partial(parse_stdin, ids),
            help=f"ID(s) or alias(es) of the {kw['service'].item.type}(s) to retrieve")

        # optional args
        single_action = self.opts.add_mutually_exclusive_group()
        single_action.add_argument(
            '-B', '--browser', action='store_true',
            help="open item URL(s) in a browser")
        single_action.add_argument(
            '-U', '--url', dest='output_url', action='store_true',
            help='output the URL(s) of the item(s)')
        self.opts.add_argument(
            '-A', '--no-attachments', action='store_false',
            help='do not show attachments',
            dest='get_attachments')
        self.opts.add_argument(
            '-C', '--no-comments', action='store_false',
            help='do not show comments',
            dest='get_comments')


class Attachments(Subcmd):

    def __init__(self, *args, desc=None, **kw):
        if desc is None:
            desc = f"get attachment(s) from {kw['service'].item.type}(s)"
        super().__init__(*args, desc=desc, **kw)

        # positional args
        self.parser.add_argument(
            'ids', metavar='ID',
            type=id_list, action=partial(parse_stdin, ids),
            help=f"attachment ID(s) (or {kw['service'].item.type} ID(s) when --item-id is used)")

        # optional args
        single_action = self.opts.add_mutually_exclusive_group()
        single_action.add_argument(
            '-B', '--browser', action='store_true',
            help="open attachment URL(s) in a browser")
        single_action.add_argument(
            '-U', '--url', dest='output_url', action='store_true',
            help='output the URL(s) of the attachment(s)')
        single_action.add_argument(
            '-V', '--view', action='store_true', dest='view_attachment',
            help='output attachment data')
        self.opts.add_argument(
            '-I', '--item-id', action='store_true',
            help='search by item ID(s) rather than attachment ID(s)')
        self.opts.add_argument(
            '--save-to',
            help='save attachment(s) into a specified dir')


class Attach(SendSubcmd):

    def __init__(self, *args, desc=None, **kw):
        if desc is None:
            desc = f"attach file to {kw['service'].item.type}(s)"
        super().__init__(*args, desc=desc, **kw)

        self.opts.add_argument(
            '-d', '--description',
            help='a long description of the attachment',
            dest='comment')
        self.opts.add_argument(
            '-t', '--title', dest='summary',
            help='a short description of the attachment (default: filename)')


class Modify(SendSubcmd):

    def __init__(self, *args, desc=None, **kw):
        if desc is None:
            desc = f"modify {kw['service'].item.type}(s)"
        super().__init__(*args, desc=desc, **kw)

        # positional args
        self.parser.add_argument(
            'ids', type=id_list, metavar='ID',
            action=partial(parse_stdin, ids),
            help=f"ID(s) of the {kw['service'].item.type}(s) to modify")

        # optional args
        self.opts.add_argument(
            '-C', '--comment-editor', action='store_true',
            help='add comment via default editor')
        self.opts.add_argument(
            '-F', '--comment-from',
            help='add comment from file. If -C is also specified, '
                 'the editor will be opened with this file as its contents')


class Create(SendSubcmd):

    def __init__(self, *args, desc=None, **kw):
        if desc is None:
            desc = f"create a new {kw['service'].item.type}"
        super().__init__(*args, desc=desc, **kw)

        self.opts.add_argument(
            '-F', '--description-from',
            help='description from contents of file')
        self.opts.add_argument(
            '--append-command',
            help='append the output of a command to the description')
        self.opts.add_argument(
            '--batch', action='store_true',
            help='do not prompt for any values')
