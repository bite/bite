from argparse import Action, ArgumentError, ArgumentTypeError
from importlib import import_module
import os
import re
import shlex
import sys

from snakeoil.cli import arghparse, tool
from snakeoil.demandload import demandload

from .alias import Aliases
from .base import get_service_cls
from .config import Config
from .exceptions import BiteError
from .objects import TimeInterval, IntRange
from .utils import block_edit, confirm

demandload('bite:const')


class ArgType(object):

    def __init__(self, service):
        self.service = service

    def __call__(self, data, stdin=False):
        if stdin:
            return self.parse_stdin(data)
        elif not sys.stdin.isatty() and data == '-':
            return data
        return self.parse(data)

    @staticmethod
    def parse(s):
        """Parse string value into expected argument type."""
        return s

    def parse_stdin(self, data):
        """Parse standard input into expected argument type."""
        return data


class StringList(ArgType):

    @staticmethod
    def parse(s):
        return [item for item in s.split(',') if item != ""]


class IDs(ArgType):

    @staticmethod
    def parse(s):
        try:
            i = int(s)
            # negative IDs are invalid
            if i < 0:
                raise ValueError
        except ValueError:
            raise ArgumentTypeError(f'invalid ID value: {s!r}')

        return i

    def parse_stdin(self, data):
        return [self.parse(x) for x in data]


class IntList(ArgType):

    @staticmethod
    def parse(s):
        l = []
        for item in s.split(','):
            try:
                l.append(int(item))
            except ValueError:
                raise ArgumentTypeError(f'invalid integer value: {item!r}')
        return l


class IDList(ArgType):

    @staticmethod
    def parse(s):
        l = []
        for item in s.split(','):
            l.append(IDs.parse(item))
        return l


class ID_Maps(ArgType):

    @staticmethod
    def parse(s):
        id_str, _sep, map_str = s.partition(':')
        id = IDs.parse(id_str)
        mapped_ids = [IDs.parse(x) for x in map_str.split(',')]
        return id, tuple(mapped_ids)

    def parse_stdin(self, data):
        return [self.parse(x) for x in data]


class ID_Str_Maps(ArgType):

    @staticmethod
    def parse(s):
        id_str, _sep, map_str = s.partition(':')
        id = IDs.parse(id_str)
        mapped_ids = map_str.split(',') if map_str else []
        return id, tuple(mapped_ids)

    def parse_stdin(self, data):
        return [self.parse(x) for x in data]


class Comment(ArgType):

    @staticmethod
    def parse(s):
        data = ''

        while True:
            if s == '__BITE_EDITOR__':
                data = block_edit('Enter a comment').strip()
            elif os.path.exists(s):
                if confirm(prompt=f'Use file for comment: {s!r}?', default=True):
                    try:
                        with open(s) as f:
                            data = f.read().strip()
                        if confirm(prompt=f'Edit comment?'):
                            data = block_edit('Edit comment', comment_from=data).strip()
                    except IOError as e:
                        raise BiteError('unable to read file: {s!r}: {e}')
            else:
                data = s
            if data or confirm('Empty comment, submit anyway?'):
                break

        return data

    def parse_stdin(self, data):
        if not data:
            raise ArgumentTypeError('no comment data provided on stdin')
        return '\n'.join(data)


class TimeIntervalArg(ArgType):

    @staticmethod
    def parse(s):
        try:
            return TimeInterval(s)
        except ValueError as e:
            raise ArgumentTypeError(e)


class IntRangeArg(ArgType):

    @staticmethod
    def parse(s):
        try:
            return IntRange(s)
        except ValueError as e:
            raise ArgumentTypeError(e)


class parse_file(Action):

    def __call__(self, parser, namespace, values, option_string=None):
        lines = (shlex.split(line.strip()) for line in values)
        setattr(namespace, self.dest, lines)


class ParseStdin(Action):

    def __init__(self, type_func=None, append=True, *args, **kwargs):
        self.type_func = type_func if type_func is not None else lambda x, stdin: x
        self.append = append
        super().__init__(*args, **kwargs)

    def __call__(self, parser, namespace, values, option_string=None):
        stdin_opt = (
            isinstance(values, (str, list, tuple)) and
            len(values) == 1 and
            values[0] == '-'
        )

        if stdin_opt and not sys.stdin.isatty():
            if option_string is None:
                option = (self.dest, self.dest)
            else:
                option = (self.dest, option_string)
            try:
                stdin = getattr(namespace, 'stdin')
                parser.error(f'argument {option[1]}: data from standard input '
                                'already being used for argument {stdin[1]}')
            except AttributeError:
                # store option for stdin check above
                setattr(namespace, 'stdin', option)
                # read args from standard input for specified option
                values = [s for s in (x.strip() for x in sys.stdin.readlines()) if s]

                # get type conversion func
                if not callable(self.type_func):
                    try:
                        self.type_func = parser._registries['type'][self.type_func]
                    except KeyError:
                        raise ArgumentTypeError(f'unknown type: {self.type_func!r}')

                # convert values to expected types
                try:
                    values = self.type_func(values, stdin=True)
                except ArgumentTypeError as e:
                    raise ArgumentError(self, e)

                # make sure values were piped via stdin for required args
                if not values and self.required:
                    raise ArgumentError(self, 'missing required values piped via stdin')

        # append multiple args by default for array-based options
        previous = getattr(namespace, self.dest, None)
        if self.append and isinstance(previous, list):
            values = previous + values

        setattr(namespace, self.dest, values)


class override_attr(Action):
    """Override or set the value of a module's attribute."""

    def __init__(self, target, attr, *args, **kwargs):
        self.target = target
        self.attr = attr
        super().__init__(*args, **kwargs)

    def __call__(self, parser, namespace, values, option_string=None):
        if isinstance(self.target, str):
            try:
                target = import_module(self.target)
            except ImportError:
                raise ArgumentTypeError(f"couldn't import module: {self.target!r}")
        else:
            target = self.target

        setattr(target, self.attr, values)


class parse_append(Action):
    def __call__(self, parser, namespace, values, option_string=None):
        if not isinstance(values, list):
            values = [values]
        current = getattr(namespace, self.dest)
        if current is None:
            setattr(namespace, self.dest, values)
        else:
            current.extend(values)


class ArgumentParser(arghparse.ArgumentParser):

    @staticmethod
    def _substitute_args(args, initial_args):
        for input_list in initial_args.input:
            line = []
            try:
                for s in args:
                    if re.match(r'^@[0-9]+$', s):
                        line.append(input_list[int(s[1:])])
                    elif re.match(r'^@@$', s):
                        line.extend(input_list)
                    else:
                        line.append(s)
                yield line
            except IndexError:
                raise RuntimeError(f'nonexistent replacement {s!r}, only {len(input_list)} values exist')

    def parse_args(self, args=None, namespace=None):
        # pull config and service settings from args if they exist
        initial_args, unparsed_args = self.parse_optionals(args, namespace)
        config_file = initial_args.pop('config_file')

        # load alias files
        aliases = Aliases()

        # check if unparsed args match any global aliases
        if unparsed_args:
            alias_unparsed_args = aliases.substitute(unparsed_args)
            # re-parse optionals to catch any added by aliases
            if unparsed_args != alias_unparsed_args:
                initial_args, unparsed_args = self.parse_optionals(alias_unparsed_args, initial_args)

        # load config files
        config = Config(
            path=config_file, connection=initial_args.connection,
            base=initial_args.base, service=initial_args.service)
        initial_args.connection = config.connection

        # pop base and service settings from the config and add them to parsed args
        # if not already specified on the command line
        for attr in ('base', 'service'):
            if getattr(initial_args, attr, None) is None:
                value = config.get(config.connection, attr, fallback=None)
                setattr(initial_args, attr, value)
            config.remove_option(config.connection, attr)

        if initial_args.base is None or initial_args.service is None:
            self.error('both arguments -b/--base and -s/--service are required '
                       'or must be specified in the config file for a connection')
        elif not re.match(r'^http(s)?://.+', initial_args.base):
            self.error(f'invalid base: {initial_args.base!r}')

        service_name = initial_args.pop('service')
        if service_name not in const.SERVICES:
            self.error(f"invalid service: {service_name!r} "
                       f"(available services: {', '.join(const.SERVICES)}")

        service_opts = get_service_cls(
            service_name, const.SERVICE_OPTS, fallbacks=(True,))(
                parser=self, service_name=service_name)

        # add service config options to args namespace
        service_opts.add_config_opts(args=initial_args, config_opts=config.opts)

        # initialize requested service
        service = get_service_cls(service_name, const.SERVICES)(**vars(initial_args))

        try:
            # add service specific main opts to the argparser
            service_opts.add_main_opts(service=service)
            # re-parse for any top level service-specific options that were added
            initial_args, unparsed_args = self.parse_optionals(unparsed_args, initial_args)
        except ArgumentError as e:
            # skip multiple main_opts() run issues during doc generation
            if 'conflicting option string' not in str(e):
                raise
        except NotImplementedError:
            # no main opts to add
            pass

        # check if unparsed args match any aliases
        if unparsed_args:
            alias_unparsed_args = aliases.substitute(
                unparsed_args, config=config, config_opts=config.opts,
                connection=initial_args.connection, service_name=service_name,
                debug=initial_args.debug)
            # re-parse optionals to catch any added by aliases
            if unparsed_args != alias_unparsed_args:
                initial_args, unparsed_args = self.parse_optionals(alias_unparsed_args, initial_args)

        # add selected subcommand options
        try:
            subcmd = unparsed_args.pop(0)
            subcmd = service_opts.add_subcmd_opts(service=service, subcmd=subcmd)
        except IndexError:
            subcmd = None

        # no more args exist or help requested, run main parser to show related output
        if subcmd is None:
            return super().parse_args()

        self.set_defaults(connection=initial_args.connection)

        if initial_args.input is not None:
            fcn_args = self._substitute_args(unparsed_args, initial_args)
        else:
            fcn_args = subcmd.parser.parse_args(unparsed_args)
            # if an arg was piped in, remove stdin attr from fcn args and reopen stdin
            stdin = fcn_args.pop('stdin', None)
            if stdin is not None:
                sys.stdin = open('/dev/tty')

        fcn_args = subcmd.finalize_args(vars(fcn_args))
        # fix called function name for nested subcommands
        if 'prog' in fcn_args:
            fcn_args['fcn' ] = fcn_args['prog'].split(' ', 1)[1].replace(' ', '_')

        # client settings that override unset service level args
        for attr in ('verbosity', 'debug'):
            if not getattr(service, attr):
                setattr(service, attr, fcn_args.get(attr))

        # set args namespace items for the client
        initial_args.service = service
        initial_args.fcn_args = fcn_args

        return initial_args


class Tool(tool.Tool):
    """Handle bite-specific commandline utility functionality."""

    def handle_exec_exception(self, e):
        """Handle bite-specific errors."""
        if isinstance(e, BiteError):
            if self.parser.debug:
                raise e
            elif self.parser.verbosity >= 0:
                msg = e.message if self.parser.verbosity else str(e)
                self.parser.error(msg)
            return 1
        else:
            # exception is unhandled here, fallback to generic handling
            super(Tool, self).handle_exec_exception(e)
