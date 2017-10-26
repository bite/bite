from argparse import (
    SUPPRESS, Action, ArgumentError, ArgumentTypeError,
    _get_action_name, _SubParsersAction, _)
import fileinput
from importlib import import_module
import importlib.util
import logging
import os
import re
import shlex
import sys

from snakeoil.cli import arghparse

from . import SERVICES
from .alias import substitute_alias
from .config import get_config
from .const import CONFIG_PATH


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
                raise ArgumentTypeError('invalid ID value: {}'.format(item))
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
                raise ArgumentTypeError('invalid ID value: {}'.format(s))
    else:
        return s

def existing_file(s):
    if not os.path.exists(s):
        msg = '"{}" does not exist'.format(s)
        raise ArgumentTypeError(msg)
    return s

class parse_file(Action):
    def __call__(self, parser, namespace, values, option_string=None):
        lines = (shlex.split(line.strip()) for line in values)
        setattr(namespace, self.dest, lines)

class parse_stdin(Action):
    def __call__(self, parser, namespace, values, option_string=None):
        if values is not None and len(values) == 1 and values[0] == '-':
            if not sys.stdin.isatty():
                if option_string is None:
                    option = (self.dest, self.dest)
                else:
                    option = (self.dest, option_string)
                try:
                    stdin = getattr(namespace, 'stdin')
                    parser.error('argument {}: data from standard input '
                                 'already being used for argument {}'.format(option[1], stdin[1]))
                except AttributeError:
                    setattr(namespace, 'stdin', option)
                    # read args from standard input for specified option
                    values = [x.strip() for x in sys.stdin.readlines() if x.strip() != '']
                    sys.stdin = open('/dev/tty')
        setattr(namespace, self.dest, values)

class parse_filters(Action):
    def __call__(self, parser, namespace, values, option_string=None):
        filters = []

        for filter_name in values.split(','):
            module_name, _, fcn_name = filter_name.partition(':')
            if fcn_name == "":
                fcn_name = module_name
                module_name = namespace.connection

            spec = importlib.util.spec_from_file_location(
                module_name, os.path.join(CONFIG_PATH, 'python'))
            if spec is None:
                parser.error('filter module not found: {}'.format(module_name))
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            try:
                filters.append(getattr(module, fcn_name))
            except AttributeError as e:
                parser.error('No function "{}" in module "{}"'.format(fcn_name, module_name))

        setattr(namespace, self.dest, filters)

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
                raise RuntimeError('nonexistent replacement "{}", only {} values exist'.format(s, len(input_list)))

    def parse_args(self, args=None, namespace=None):
        initial_args, unparsed_args = self.parse_optionals(args, namespace)

        # allow symlinks to bite to override the connection type
        if os.path.basename(sys.argv[0]) != 'bite':
            initial_args.connection = os.path.basename(sys.argv[0])

        # get settings from the config file
        get_config(initial_args, self)

        logger = logging.getLogger(__name__)
        #logger.setLevel(logging.DEBUG)

        if initial_args.base is None or initial_args.service is None:
            self.error('both arguments -b/--base and -s/--service are required '
                       'or must be specified in the config file for a connection')

        service_name = initial_args.service
        if service_name not in SERVICES:
            self.error('{!r} service is unknown (available services: {})'.format(
                service_name, ', '.join(SERVICES)))

        # add subcommand parsers for the specified service type
        subparsers = self.add_subparsers(help='help for subcommands')

        try:
            service_args = import_module('bite.args.' + service_name.replace('-', '.'))
        except ImportError:
            self.error('failed getting {!r} service options'.format(service_name))

        # add any additional service specific top level commands
        try:
            service_args.maincmds(subcommands)
        except AttributeError:
            pass

        # add subcommands
        service_args.subcmds(subparsers)

        # check if unparsed args match any aliases
        if unparsed_args:
            unparsed_args = substitute_alias(initial_args, unparsed_args)

        self.set_defaults(connection=initial_args.connection)

        if initial_args.input is not None:
            fcn_args = self._substitute_args(unparsed_args, initial_args)

        args = arghparse.Namespace(**vars(initial_args))
        fcn_args = super().parse_args(unparsed_args, initial_args)
        args = vars(args)
        fcn_args = {k:v for k,v in vars(fcn_args).items() if k not in args}
        for i in ['dry_run', 'jobs']:
            if i in args:
                fcn_args[i] = args[i]
        initial_args.fcn_args = fcn_args
        return initial_args
