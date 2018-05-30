from argparse import (
    SUPPRESS, Action, ArgumentError, ArgumentTypeError,
    _get_action_name, _SubParsersAction, _)
from importlib import import_module
import os
import re
import shlex
import sys

from snakeoil.cli import arghparse, tool
from snakeoil.demandload import demandload

from . import get_service_cls, service_classes
from .alias import Aliases
from .config import get_config
from .exceptions import BiteError
from .objects import TimeInterval
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


class IDList(ArgType):

    @staticmethod
    def parse(s):
        try:
            l = []
            for item in s.split(','):
                l.append(int(item))
            return l
        except:
            raise ArgumentTypeError(f'invalid ID value: {item!r}')


class IDs(ArgType):

    @staticmethod
    def parse(s):
        try:
            return int(s)
        except:
            raise ArgumentTypeError(f'invalid ID value: {s!r}')

    def parse_stdin(self, data):
        return [self.parse(x) for x in data]


class ID_Maps(ArgType):

    @staticmethod
    def parse(s):
        id_str, _sep, a_str = s.partition(':')
        try:
            id = int(id_str)
        except ValueError:
            raise ArgumentTypeError(f'invalid ID value: {id_str!r}')

        a_ids = []
        try:
            for x in a_str.split(','):
                a_ids.append(int(x))
        except ValueError:
            raise ArgumentTypeError(f'invalid attachment ID value: {x!r}')

        return id, tuple(a_ids)

    def parse_stdin(self, data):
        return [self.parse(x) for x in data]


class ID_Str_Maps(ArgType):

    @staticmethod
    def parse(s):
        id_str, _sep, a_str = s.partition(':')
        try:
            id = int(id_str)
        except ValueError:
            raise ArgumentTypeError(f'invalid ID value: {id_str!r}')

        a_ids = a_str.split(',') if a_str else []
        return id, tuple(a_ids)

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

    def parse_optionals(self, args=None, namespace=None):
        """Parse optional arguments until the first positional or -h/--help.

        This is used to allow multiple shortcuts (like -c or -h) at both the
        global command level and the subcommand level. Otherwise, the argparse
        module wouldn't allow two of the same shortcuts to exist at the same
        time.
        """
        if args is None:
            # args default to the system args
            args = sys.argv[1:]
        else:
            # make sure that args are mutable
            args = list(args)

        # default Namespace built from parser defaults
        if namespace is None:
            namespace = arghparse.Namespace()

        # add any action defaults that aren't present
        for action in self._actions:
            if action.dest is not SUPPRESS:
                if not hasattr(namespace, action.dest):
                    if action.default is not SUPPRESS:
                        setattr(namespace, action.dest, action.default)

        # add any parser defaults that aren't present
        for dest in self._defaults:
            if not hasattr(namespace, dest):
                setattr(namespace, dest, self._defaults[dest])

        # parse the arguments and exit if there are any errors
        try:
            return self._parse_optionals(args, namespace)
        except ArgumentError:
            err = sys.exc_info()[1]
            self.error(str(err))

    def _parse_optionals(self, arg_strings, namespace):
        # replace arg strings that are file references
        if self.fromfile_prefix_chars is not None:
            arg_strings = self._read_args_from_files(arg_strings)

        # map all mutually exclusive arguments to the other arguments
        # they can't occur with
        action_conflicts = {}
        for mutex_group in self._mutually_exclusive_groups:
            group_actions = mutex_group._group_actions
            for i, mutex_action in enumerate(mutex_group._group_actions):
                conflicts = action_conflicts.setdefault(mutex_action, [])
                conflicts.extend(group_actions[:i])
                conflicts.extend(group_actions[i + 1:])

        # find all option indices, and determine the arg_string_pattern
        # which has an 'O' if there is an option at an index,
        # an 'A' if there is an argument, or a '-' if there is a '--'
        option_string_indices = {}
        arg_string_pattern_parts = []
        arg_strings_iter = iter(arg_strings)
        for i, arg_string in enumerate(arg_strings_iter):

            # all args after -- are non-options
            if arg_string == '--':
                arg_string_pattern_parts.append('-')
                for arg_string in arg_strings_iter:
                    arg_string_pattern_parts.append('A')

            # otherwise, add the arg to the arg strings
            # and note the index if it was an option
            else:
                option_tuple = self._parse_optional(arg_string)
                if option_tuple is None:
                    pattern = 'A'
                else:
                    option_string_indices[i] = option_tuple
                    pattern = 'O'
                arg_string_pattern_parts.append(pattern)

        # join the pieces together to form the pattern
        arg_strings_pattern = ''.join(arg_string_pattern_parts)

        # converts arg strings to the appropriate and then takes the action
        seen_actions = set()
        seen_non_default_actions = set()

        def take_action(action, argument_strings, option_string=None):
            seen_actions.add(action)
            argument_values = self._get_values(action, argument_strings)

            # error if this argument is not allowed with other previously
            # seen arguments, assuming that actions that use the default
            # value don't really count as "present"
            if argument_values is not action.default:
                seen_non_default_actions.add(action)
                for conflict_action in action_conflicts.get(action, []):
                    if conflict_action in seen_non_default_actions:
                        msg = _('not allowed with argument %s')
                        action_name = _get_action_name(conflict_action)
                        raise ArgumentError(action, msg % action_name)

            # take the action if we didn't receive a SUPPRESS value
            # (e.g. from a default)
            if argument_values is not SUPPRESS:
                action(self, namespace, argument_values, option_string)

        # function to convert arg_strings into an optional action
        def consume_optional(start_index):

            # get the optional identified at this index
            option_tuple = option_string_indices[start_index]
            action, option_string, explicit_arg = option_tuple

            # identify additional optionals in the same arg string
            # (e.g. -xyz is the same as -x -y -z if no args are required)
            match_argument = self._match_argument
            action_tuples = []
            while True:

                # if we found no optional action, skip it
                if action is None:
                    extras.append(arg_strings[start_index])
                    return start_index + 1

                # if we match help options, skip them for now so subparsers
                # show up in the help output
                if arg_strings[start_index] in ('-h', '--help'):
                    extras.append(arg_strings[start_index])
                    return start_index + 1

                # if there is an explicit argument, try to match the
                # optional's string arguments to only this
                if explicit_arg is not None:
                    arg_count = match_argument(action, 'A')

                    # if the action is a single-dash option and takes no
                    # arguments, try to parse more single-dash options out
                    # of the tail of the option string
                    chars = self.prefix_chars
                    if arg_count == 0 and option_string[1] not in chars:
                        action_tuples.append((action, [], option_string))
                        char = option_string[0]
                        option_string = char + explicit_arg[0]
                        new_explicit_arg = explicit_arg[1:] or None
                        optionals_map = self._option_string_actions
                        if option_string in optionals_map:
                            action = optionals_map[option_string]
                            explicit_arg = new_explicit_arg
                        else:
                            msg = _('ignored explicit argument %r')
                            raise ArgumentError(action, msg % explicit_arg)

                    # if the action expect exactly one argument, we've
                    # successfully matched the option; exit the loop
                    elif arg_count == 1:
                        stop = start_index + 1
                        args = [explicit_arg]
                        action_tuples.append((action, args, option_string))
                        break

                    # error if a double-dash option did not use the
                    # explicit argument
                    else:
                        msg = _('ignored explicit argument %r')
                        raise ArgumentError(action, msg % explicit_arg)

                # if there is no explicit argument, try to match the
                # optional's string arguments with the following strings
                # if successful, exit the loop
                else:
                    start = start_index + 1
                    selected_patterns = arg_strings_pattern[start:]
                    arg_count = match_argument(action, selected_patterns)
                    stop = start + arg_count
                    args = arg_strings[start:stop]
                    action_tuples.append((action, args, option_string))
                    break

            # add the Optional to the list and return the index at which
            # the Optional's string args stopped
            assert action_tuples
            for action, args, option_string in action_tuples:
                take_action(action, args, option_string)
            return stop

        # the list of Positionals left to be parsed; this is modified
        # by consume_positionals()
        positionals = self._get_positional_actions()

        # function to convert arg_strings into positional actions
        def consume_positionals(start_index):
            # match as many Positionals as possible
            match_partial = self._match_arguments_partial
            selected_pattern = arg_strings_pattern[start_index:]
            arg_counts = match_partial(positionals, selected_pattern)

            # slice off the appropriate arg strings for each Positional
            # and add the Positional and its args to the list
            for action, arg_count in zip(positionals, arg_counts):
                args = arg_strings[start_index: start_index + arg_count]
                start_index += arg_count
                take_action(action, args)

            # slice off the Positionals that we just parsed and return the
            # index at which the Positionals' string args stopped
            positionals[:] = positionals[len(arg_counts):]
            return start_index

        # consume Positionals and Optionals alternately, until we have
        # passed the last option string
        extras = []
        start_index = 0
        if option_string_indices:
            max_option_string_index = max(option_string_indices)
        else:
            max_option_string_index = -1
        while start_index <= max_option_string_index:

            # consume any Positionals preceding the next option
            next_option_string_index = min([
                index
                for index in option_string_indices
                if index >= start_index])
            if start_index != next_option_string_index:
                # positionals_end_index = consume_positionals(start_index)
                positionals_end_index = start_index

                # only try to parse the next optional if we didn't consume
                # the option string during the positionals parsing
                if positionals_end_index >= start_index:
                    start_index = positionals_end_index
                    break
                else:
                    start_index = positionals_end_index

            # if we consumed all the positionals we could and we're not
            # at the index of an option string, there were extra arguments
            if start_index not in option_string_indices:
                strings = arg_strings[start_index:next_option_string_index]
                extras.extend(strings)
                start_index = next_option_string_index

            # consume the next optional and any arguments for it
            start_index = consume_optional(start_index)

        # consume any positionals following the last Optional
        # stop_index = consume_positionals(start_index)
        stop_index = start_index

        # if we didn't consume all the argument strings, there were extras
        extras.extend(arg_strings[stop_index:])

        # make sure all required actions were present and also convert
        # action defaults which were not given as arguments
        required_actions = []
        for action in self._actions:
            if action not in seen_actions:
                # ignore required subcommands as they'll be handled later
                if action.required and not isinstance(action, _SubParsersAction):
                    required_actions.append(_get_action_name(action))
                else:
                    # Convert action default now instead of doing it before
                    # parsing arguments to avoid calling convert functions
                    # twice (which may fail) if the argument was given, but
                    # only if it was defined already in the namespace
                    if (action.default is not None and
                        isinstance(action.default, str) and
                        hasattr(namespace, action.dest) and
                        action.default is getattr(namespace, action.dest)):
                        setattr(namespace, action.dest,
                                self._get_value(action, action.default))

        if required_actions:
            self.error(_('the following arguments are required: %s') %
                       ', '.join(required_actions))

        # make sure all required groups had one option present
        for group in self._mutually_exclusive_groups:
            if group.required:
                for action in group._group_actions:
                    if action in seen_non_default_actions:
                        break

                # if no actions were used, report the error
                else:
                    names = [_get_action_name(action)
                             for action in group._group_actions
                             if action.help is not SUPPRESS]
                    msg = _('one of the arguments %s is required')
                    self.error(msg % ' '.join(names))

        # return the updated namespace and the extra arguments
        return namespace, extras

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
        config, config_opts = get_config(initial_args, config_file=config_file)

        if initial_args.base is None or initial_args.service is None:
            self.error('both arguments -b/--base and -s/--service are required '
                       'or must be specified in the config file for a connection')
        elif not re.match(r'^http(s)?://.+', initial_args.base):
            self.error(f'invalid base: {initial_args.base!r}')

        service_name = initial_args.service
        if service_name not in const.SERVICES:
            self.error(f"invalid service: {service_name!r} "
                       f"(available services: {', '.join(const.SERVICES)}")

        fallbacks = list(service_classes(service_name))[1:]
        service_opts = get_service_cls(
            service_name, const.SERVICE_OPTS, fallbacks=fallbacks)(
                parser=self, service_name=service_name)

        # add service config options to args namespace
        service_opts.add_config_opts(args=initial_args, config_opts=config_opts)

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
                unparsed_args, config_opts=config_opts,
                connection=initial_args.connection, service_name=service_name)
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

        # client settings that override unset service level args
        for attr in ('verbose', 'debug'):
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
            else:
                msg = e.message if self.parser.verbose else str(e)
                self.parser.error(msg)
            return 1
        else:
            # exception is unhandled here, fallback to generic handling
            super(Tool, self).handle_exec_exception(e)
