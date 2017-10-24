import os
import re

import configparser
from configparser import NoOptionError, NoSectionError, InterpolationMissingOptionError

from bite.exceptions import CliError

if 'XDG_CONFIG_HOME' in os.environ:
    CONFIG_DIR = os.path.join(os.environ['XDG_CONFIG_HOME'], 'bite')
else:
    CONFIG_DIR = os.path.expanduser('~/.config/bite/')

class BiteInterpolation(configparser.ExtendedInterpolation):
    """Modified version of ExtendedInterpolation

    Uses %{option} for options local to the current section or default section
    and %{section:option} for options in different sections.
    """

    _KEYCRE = re.compile(r"\%\{([^}]+)\}")

    def before_get(self, parser, section, option, value, defaults):
        L = []
        self._interpolate_some(parser, option, L, value, section, defaults, 1)
        return ''.join(L)

    def before_set(self, parser, section, option, value):
        tmp_value = value.replace('%%', '') # escaped dollar signs
        tmp_value = self._KEYCRE.sub('', tmp_value) # valid syntax
        if '%' in tmp_value:
            raise ValueError("invalid interpolation syntax in %r at "
                             "position %d" % (value, tmp_value.find('%')))
        return value

    def _interpolate_some(self, parser, option, accum, rest, section, map,
                          depth):
        if depth > configparser.MAX_INTERPOLATION_DEPTH:
            raise InterpolationDepthError(option, section, rest)
        while rest:
            p = rest.find("%")
            if p < 0:
                accum.append(rest)
                return
            if p > 0:
                accum.append(rest[:p])
                rest = rest[p:]
            # p is no longer used
            c = rest[1:2]
            if c == "%":
                accum.append("%")
                rest = rest[2:]
            elif c == "{":
                m = self._KEYCRE.match(rest)
                if m is None:
                    raise InterpolationSyntaxError(option, section,
                        "bad interpolation variable reference %r" % rest)
                path = m.group(1).split(':')
                rest = rest[m.end():]
                sect = section
                opt = option
                try:
                    if len(path) == 1:
                        opt = parser.optionxform(path[0])
                        try:
                            v = map[opt]
                        except KeyError:
                            sect = 'default'
                            v = parser.get(sect, opt, raw=True)
                    elif len(path) == 2:
                        sect = path[0]
                        opt = parser.optionxform(path[1])
                        v = parser.get(sect, opt, raw=True)
                    else:
                        raise InterpolationSyntaxError(
                            option, section,
                            "More than one ':' found: %r" % (rest,))
                except (KeyError, NoSectionError, NoOptionError):
                    raise InterpolationMissingOptionError(
                        option, section, rest, ":".join(path))
                if "%" in v:
                    self._interpolate_some(parser, opt, accum, v, sect,
                                           dict(parser.items(sect, raw=True)),
                                           depth + 1)
                else:
                    if v.startswith('!'):
                        v = v[1:]
                    accum.append(v)
            else:
                raise InterpolationSyntaxError(
                    option, section,
                    "'%' must be followed by '%' or '{', "
                    "found: %r" % (rest,))

def parse_config(config_path):
    parser = configparser.ConfigParser(interpolation=BiteInterpolation())
    try:
        parser.read(config_path)
    except IOError:
        return
    except Exception as e:
        raise
    return parser

def config_option(parser, get, section, option):
    if parser.has_option(section, option):
        try:
            if get(section, option) != '':
                return get(section, option)
            else:
                parser.error('"{}" is not set'.format(option))
        except ValueError as e:
            parser.error('option "{}" is not in the right format: {}'.format(option, str(e)))

def set_config_option(config_file, section, option, value, exists=False):
    """Save a config option and value to a specified config file.

    This function doesn't use the ConfigParser class because that would remove
    all comments and other non-functional lines from the config file on saving.
    """

    with open(config_file, 'r+') as f:
        config = f.readlines()

        for i in xrange(len(config)):
            # find the beginning of the matching section
            if re.match(r'^\[{}\].*\n$'.format(section), config[i]):
                break

        if i >= len(config)-1:
            raise RuntimeError('Cannot find section "{}" in config file'.format(section))

        config_option = '{}: {}\n'.format(option, value)

        while True:
            i += 1
            if not exists:
                # insert the option after the last line of the matching section
                if re.match(r'^(\s*|#.*|\[\w+\])\n$', config[i]):
                    config.insert(i, config_option)
                    break
            else:
                # overwrite the existing option
                if re.match(r'^{}: '.format(option), config[i]):
                    config[i] = config_option
                    break

        f.seek(0)
        f.truncate()
        f.writelines(config)

def get_matching_options(parser, section, regex):
    values = []
    for (name, value) in parser.items(section):
        if re.match(regex, name):
            values.append((name, value))
    return values

def get_config_option(config_file, section, option):
    parser = configparser.ConfigParser()
    with open(config_file, 'r+') as f:
        parser.readfp(f)

    try:
        value = parser.get(section, option)
    except configparser.NoOptionError:
        raise ValueError('No option "{}" for section "{}"'.format(option, section))
    except configparser.NoSectionError:
        raise ValueError('No section "{}"'.format(section))
    return value

def fill_config_option(args, parser, get, section, option):
    value = config_option(parser, get, section, option)
    if value is not None:
        setattr(args, option, value)

def fill_config(args, parser, section):
    fill_config_option(args, parser, parser.get, section, 'service')
    fill_config_option(args, parser, parser.get, section, 'base')
    fill_config_option(args, parser, parser.get, section, 'user')
    fill_config_option(args, parser, parser.get, section, 'password')
    fill_config_option(args, parser, parser.get, section, 'passwordcmd')
    fill_config_option(args, parser, parser.get, section, 'auth_token')
    fill_config_option(args, parser, parser.getboolean, section, 'skip_auth')
    fill_config_option(args, parser, parser.getint, section, 'columns')
    fill_config_option(args, parser, parser.getint, section, 'timeout')
    fill_config_option(args, parser, parser.getint, section, 'jobs')
    fill_config_option(args, parser, parser.get, section, 'encoding')
    fill_config_option(args, parser, parser.getboolean, section, 'verify')
    fill_config_option(args, parser, parser.getboolean, section, 'quiet')
    fill_config_option(args, parser, parser.get, section, 'suffix')

def get_config(args, parser):
    args.config_dir = CONFIG_DIR
    if args.config_file is None:
        args.config_file = os.path.join(args.config_dir, 'config')

    config = configparser.ConfigParser(interpolation=BiteInterpolation())

    # load service settings
    services_dir = os.path.join(args.config_dir, 'services')
    config.read([os.path.join(services_dir, x) for x in os.listdir(services_dir)])

    try:
        with open(args.config_file) as f:
            config.read_file(f)
    except IOError as e:
        raise CliError('cannot load config file "{}": {}'.format(e.filename, e.strerror))

    args.config = config
    args.aliases = parse_config(os.path.join(args.config_dir, 'aliases'))

    if args.service is None and args.base is None:
        if 'default' in config.sections():
            fill_config(args, config, 'default')
        if args.connection is None:
            args.connection = config_option(config, config.get, 'default', 'connection')

    if args.connection in config.sections():
        fill_config(args, config, args.connection)
    elif args.connection is not None:
        parser.error('connection "{}" does not exist in config file'.format(args.connection))
