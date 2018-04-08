from argparse import (
    SUPPRESS, Action, ArgumentError, ArgumentTypeError,
    _get_action_name, _SubParsersAction, _)
from importlib import import_module
import logging
import os
import re
import shlex
import sys

from snakeoil.cli import arghparse, tool
from snakeoil.demandload import demandload
from snakeoil.sequences import iflatten_instance

from . import get_service_cls
from .alias import substitute_alias
from .config import get_config
from .exceptions import BiteError

demandload('bite:const')


def string_list(s):
    if sys.stdin.isatty() or s != '-':
        return [item for item in s.split(',') if item != ""]
    else:
        return s


def id_list(s):
    if sys.stdin.isatty() or s != '-':
        try:
            l = []
            for item in s.split(','):
                l.append(int(item))
            return l
        except:
            if item == '-':
                raise ArgumentTypeError("'-' is only valid when piping data in")
            else:
                raise ArgumentTypeError(f'invalid ID value: {repr(item)}')
    else:
        return s


def ids(s):
    if sys.stdin.isatty() or s != '-':
        try:
            return int(s)
        except:
            if s == '-':
                raise ArgumentTypeError("'-' is only valid when piping data in")
            else:
                raise ArgumentTypeError(f'invalid ID value: {repr(s)}')
    else:
        return s


def existing_file(s):
    if not os.path.exists(s):
        raise ArgumentTypeError(f'nonexistent file: {repr(s)}')
    return s


class parse_file(Action):
    def __call__(self, parser, namespace, values, option_string=None):
        lines = (shlex.split(line.strip()) for line in values)
        setattr(namespace, self.dest, lines)


class parse_stdin(Action):

    def __init__(self, convert_type=None, append=True, *args, **kwargs):
        self.convert_type = convert_type if convert_type is not None else lambda x: x
        self.append = append
        super().__init__(*args, **kwargs)

    def __call__(self, parser, namespace, values, option_string=None):
        stdin_opt = (
            isinstance(values, (str, list, tuple)) and
            len(values) == 1 and
            values[0] == '-'
        )

        if stdin_opt:
            if not sys.stdin.isatty():
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
                    values = []
                    for x in sys.stdin.readlines():
                        v = x.strip()
                        if v:
                            try:
                                values.extend(iflatten_instance([self.convert_type(v)]))
                            except ArgumentTypeError as e:
                                raise ArgumentError(self, e)

                    # make sure values were piped via stdin for required args
                    if not values and self.required:
                        raise ArgumentError(self, 'missing required values piped via stdin')

        # append multiple args by default for array-based options
        previous = getattr(namespace, self.dest)
        if self.append and isinstance(previous, list):
            values = previous + values

        setattr(namespace, self.dest, values)


class override_attr(Action):
    """Override or set the value of a module's attribute."""

    def __init__(self, attr, *args, **kwargs):
        try:
            self.module, self.attr = attr.rsplit('.', 1)
        except ValueError:
            raise ArgumentTypeError('full path to attribute required')
        super().__init__(*args, **kwargs)

    def __call__(self, parser, namespace, values, option_string=None):
        try:
            setattr(import_module(self.module), self.attr, values)
        except ImportError:
            raise ArgumentTypeError(f"couldn't import module: {repr(self.module)}")


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
                raise RuntimeError(f'nonexistent replacement {repr(s)}, only {len(input_list)} values exist')

    def parse_args(self, args=None, namespace=None):
        # pull config and service settings from args if they exist
        from .scripts.bite import config_opts_parser
        initial_args, unparsed_args = config_opts_parser.parse_optionals(args, namespace)
        config_file = initial_args.pop('config_file')

        # load config files
        config, aliases = get_config(initial_args, config_file=config_file)

        if initial_args.base is None or initial_args.service is None:
            self.error('both arguments -b/--base and -s/--service are required '
                       'or must be specified in the config file for a connection')
        elif not re.match(r'^http(s)?://.+', initial_args.base):
            self.error(f'invalid base: {repr(initial_args.base)}')

        service = initial_args.service
        if service not in const.SERVICES:
            self.error(f"invalid service: {repr(service)} (available services: {', '.join(const.SERVICES)}")

        service_opts = get_service_cls(
            service, const.SERVICE_OPTS)(parser=self, service_name=service)

        # add service config options to args namespace
        service_opts.add_config_opts(
            args=initial_args, config_opts=config.items(initial_args.connection))

        logger = logging.getLogger(__name__)
        #logger.setLevel(logging.DEBUG)

        # re-parse for any top level service-specific options that were just added
        initial_args, unparsed_args = self.parse_optionals(unparsed_args, initial_args)

        # replace service attr with service object
        initial_args.service = get_service_cls(service, const.SERVICES)(**vars(initial_args))

        # add subcommands
        service_opts.add_subcmds(service=initial_args.service)

        # check if unparsed args match any aliases
        if unparsed_args:
            service_type = initial_args.service._service.split('-')[0]
            unparsed_args = substitute_alias(
                initial_args.connection, service_type, aliases, unparsed_args)

        self.set_defaults(connection=initial_args.connection)

        if initial_args.input is not None:
            fcn_args = self._substitute_args(unparsed_args, initial_args)

        args = arghparse.Namespace(**vars(initial_args))
        fcn_args = super().parse_args(unparsed_args, initial_args)

        # if an arg was piped in, remove stdin attr from fcn args and reopen stdin
        stdin = fcn_args.pop('stdin', None)
        if stdin is not None:
            sys.stdin = open('/dev/tty')

        args = vars(args)
        fcn_args = {k: v for k, v in vars(fcn_args).items() if k not in args and v}
        extra_fcn_args = {'dry_run'}
        for x in extra_fcn_args.intersection(args):
            fcn_args[x] = args[x]
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
                msg = e.message if getattr(self.options, 'verbose', False) else str(e)
                self.parser.error(msg)
            return 1
        else:
            # exception is unhandled here, fallback to generic handling
            super(Tool, self).handle_exec_exception(e)
