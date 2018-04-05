import configparser
from functools import partial
import os
import re

from snakeoil.demandload import demandload

from .exceptions import BiteError

demandload('bite:const')


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
            raise configparser.InterpolationDepthError(option, section, rest)
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
                    raise configparser.InterpolationSyntaxError(
                        option, section,
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
                            sect = parser.default_section
                            v = parser.get(sect, opt, raw=True)
                    elif len(path) == 2:
                        sect = path[0]
                        opt = parser.optionxform(path[1])
                        v = parser.get(sect, opt, raw=True)
                    else:
                        raise configparser.InterpolationSyntaxError(
                            option, section,
                            "More than one ':' found: %r" % (rest,))
                except (KeyError, configparser.NoSectionError, configparser.NoOptionError):
                    raise configparser.InterpolationMissingOptionError(
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
                raise configparser.InterpolationSyntaxError(
                    option, section,
                    "'%' must be followed by '%' or '{', "
                    "found: %r" % (rest,))

def config_option(parser, get, section, option):
    if parser.has_option(section, option):
        try:
            if get(section, option) != '':
                return get(section, option)
            else:
                parser.error(f'{repr(option)} is not set')
        except ValueError as e:
            parser.error(f'option {repr(option)} is not in the right format: {e}')

def set_config_option(config_file, section, option, value, exists=False):
    """Save a config option and value to a specified config file.

    This function doesn't use the ConfigParser class because that would remove
    all comments and other non-functional lines from the config file on saving.
    """

    with open(config_file, 'r+') as f:
        config = f.readlines()

        for i in range(len(config)):
            # find the beginning of the matching section
            if re.match(fr'^\[{section}\].*\n$', config[i]):
                break

        if i >= len(config) - 1:
            raise RuntimeError(f'Cannot find section {repr(section)} in config file')

        config_option = f'{option}: {value}\n'

        while True:
            i += 1
            if not exists:
                # insert the option after the last line of the matching section
                if re.match(r'^(\s*|#.*|\[\w+\])\n$', config[i]):
                    config.insert(i, config_option)
                    break
            else:
                # overwrite the existing option
                if re.match(fr'^{option}: ', config[i]):
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
        raise ValueError(f'No option {repr(option)} for section {repr(section)}')
    except configparser.NoSectionError:
        raise ValueError(f'No section {repr(section)}')
    return value

def fill_config(settings, parser, section):
    def fill_config_option(settings, parser, section, get, option, func=None):
        func = func if func is not None else lambda x: x
        value = config_option(parser, get, section, option)
        if value is not None:
            settings[option] = func(value)

    parse_option = partial(fill_config_option, settings, parser, section)
    parse_option(parser.get, 'service')
    parse_option(parser.get, 'base')
    parse_option(parser.get, 'user')
    parse_option(parser.get, 'password')
    parse_option(parser.get, 'passwordcmd')
    parse_option(parser.get, 'auth_token')
    parse_option(parser.get, 'auth_file')
    parse_option(parser.getboolean, 'skip_auth')
    parse_option(parser.getint, 'columns')
    parse_option(parser.getint, 'concurrent')
    parse_option(parser.getint, 'timeout')
    parse_option(parser.getint, 'max_results')
    parse_option(parser.getboolean, 'verify')
    parse_option(parser.getboolean, 'quiet')
    parse_option(parser.get, 'suffix')


def get_config(args, parser):
    config = configparser.ConfigParser()
    aliases = configparser.ConfigParser(interpolation=BiteInterpolation())

    config_settings = {
        'config': config,
        'aliases': aliases,
    }

    # load config files
    system_config = os.path.join(const.CONFIG_PATH, 'bite.conf')
    user_config = os.path.join(const.USER_CONFIG_PATH, 'bite.conf')
    try:
        with open(system_config) as f:
            config.read_file(f)
        config.read(user_config)
    except IOError as e:
        raise BiteError(f'cannot load config file {repr(e.filename)}: {e.strerror}')

    if args.service is None or args.base is None:
        if args.connection is None:
            args.connection = config.defaults().get('connection', None)
            config_settings['connection'] = args.connection
        if not any ((args.service, args.base)) and args.connection is None:
            raise BiteError('no connection specified and no default connection set')

    # Load system connection settings and then user connection settings --
    # later settings override earlier ones. Note that only the service config
    # files matching the name of the selected connection are loaded.
    if args.connection is not None:
        for service_dir in (os.path.join(const.DATA_PATH, 'services'),
                            os.path.join(const.USER_DATA_PATH, 'services')):
            for root, _, files in os.walk(service_dir):
                config.read(os.path.join(root, f) for f in files if f == args.connection)

    if config.has_section(args.connection):
        fill_config(config_settings, config, args.connection)
    elif args.connection:
        parser.error(f'unknown connection: {repr(args.connection)}')

    # load alias files
    system_aliases = os.path.join(const.CONFIG_PATH, 'aliases')
    user_aliases = os.path.join(const.USER_CONFIG_PATH, 'aliases')
    try:
        with open(system_aliases) as f:
            aliases.read_file(f)
        aliases.read(user_aliases)
    except IOError as e:
        raise BiteError(f'cannot load aliases file {repr(e.filename)}: {e.strerror}')
    except (configparser.DuplicateSectionError, configparser.DuplicateOptionError) as e:
        raise BiteError(e)

    return config_settings
