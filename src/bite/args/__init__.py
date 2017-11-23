from ..argparser import string_list


def subcmd(service_cls, name=None):
    """Register service subcommands."""
    def wrapped(cls, *args, **kwds):
        subcmd_name = name if name is not None else cls.__name__.lower()
        if service_cls._subcmds is None:
            service_cls._subcmds = [(subcmd_name, cls)]
        else:
            service_cls._subcmds.append((subcmd_name, cls))
        return cls
    return wrapped


class Subcmd(object):

    def __init__(self, parser, service, name=None, desc=None):
        name = name if name is not None else self.__class__.__name__.lower()
        self.parser = parser.add_parser(
            name, verbose=False, quiet=False, color=False, description=desc)
        self.parser.set_defaults(fcn=name)
        self.opts = self.parser.add_argument_group('{} options'.format(name.capitalize()))


class ServiceOpts(object):

    _service = None
    _subcmds = None

    def __init__(self, parser, service_name):
        self.parser = parser

        from ..scripts.bite import service_specific_opts
        self.service_opts = service_specific_opts
        self.service_opts.title = service_name.split('-')[0].capitalize() + ' specific options'

        self.main_opts()

    def main_opts(self):
        """Add service specific top-level options."""

    def add_subcmds(self, service):
        subcmd_parser = self.parser.add_subparsers(help='help for subcommands')
        if self._subcmds is not None:
            for name, cls in self._subcmds:
                cls(parser=subcmd_parser, service=service, name=name)


class SendSubcmd(Subcmd):

    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        self.opts.add_argument(
            '--ask', action='store_true',
            help='require confirmation before submitting modifications')


class ReceiveSubcmd(Subcmd):

    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        self.opts.add_argument(
            '-f', '--fields', type=string_list,
            metavar='FIELD | FIELD,FIELD,...',
            help='fields to output')


class Search(ReceiveSubcmd):

    def __init__(self, *args, desc=None, **kw):
        if desc is None:
            desc = 'search for {}s'.format(kw['service'].item.type)
        super().__init__(*args, desc=desc, **kw)

        self.opts.add_argument('--limit',
            type=int,
            help='Limit the number of records returned in a search')
        self.opts.add_argument('--offset',
            type=int,
            help='Set the start position for a search')


class Get(ReceiveSubcmd):

    def __init__(self, *args, desc=None, **kw):
        if desc is None:
            desc = 'get {}(s)'.format(kw['service'].item.type)
        super().__init__(*args, desc=desc, **kw)

        self.opts.add_argument('-a', '--no-attachments',
            action='store_false',
            help='do not show attachments',
            dest='get_attachments')
        self.opts.add_argument('-c', '--no-comments',
            action='store_false',
            help='do not show comments',
            dest='get_comments')
        self.opts.add_argument('-B', '--browser',
            action='store_true',
            help="open item page in a browser")


class Attachments(Subcmd):

    def __init__(self, *args, desc=None, **kw):
        if desc is None:
            desc = 'get attachment(s) from {}(s)'.format(kw['service'].item.type)
        super().__init__(*args, desc=desc, **kw)

        single_action = self.opts.add_mutually_exclusive_group()
        single_action.add_argument('-U', '--url',
            dest='output_url',
            action='store_true',
            help='output the URL of the attachment')
        single_action.add_argument('-V', '--view',
            action='store_true',
            dest='view_attachment',
            help='output attachment data')
        single_action.add_argument('-B', '--browser',
            action='store_true',
            help="open item page in a browser")
        self.opts.add_argument('-I', '--item-id',
            action='store_true',
            help='search by item ID(s) rather than attachment ID(s)')
        self.opts.add_argument('--save-to',
            help='save attachments into a specified dir')


class Attach(SendSubcmd):

    def __init__(self, *args, desc=None, **kw):
        if desc is None:
            desc = 'attach file to {}(s)'.format(kw['service'].item.type)
        super().__init__(*args, desc=desc, **kw)

        self.opts.add_argument('-d', '--description',
            help='a long description of the attachment',
            dest='comment')
        self.opts.add_argument('-t', '--title',
            help='a short description of the attachment (default: filename)',
            dest='summary')


class Modify(SendSubcmd):

    def __init__(self, *args, desc=None, **kw):
        if desc is None:
            desc = 'modify {}(s)'.format(kw['service'].item.type)
        super().__init__(*args, desc=desc, **kw)

        self.opts.add_argument('-C', '--comment-editor',
            action='store_true',
            help='add comment via default editor')
        self.opts.add_argument('-F', '--comment-from',
            help='add comment from file. If -C is also specified, '
                 'the editor will be opened with this file as its contents')


class Create(SendSubcmd):

    def __init__(self, *args, desc=None, **kw):
        if desc is None:
            desc = 'create a new {}'.format(kw['service'].item.type)
        super().__init__(*args, desc=desc, **kw)

        self.opts.add_argument('-F' , '--description-from',
            help='description from contents of file')
        self.opts.add_argument('--append-command',
            help='append the output of a command to the description')
        self.opts.add_argument('--batch',
            action='store_true',
            help='do not prompt for any values')
