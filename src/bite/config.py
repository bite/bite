import configparser
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


def load_config(config_name='bite.conf', config=None):
    """Load system and user configuration files."""
    config = config if config is not None else configparser.ConfigParser()

    system_config = os.path.join(const.CONFIG_PATH, config_name)
    user_config = os.path.join(const.USER_CONFIG_PATH, config_name)
    try:
        with open(system_config) as f:
            config.read_file(f)
        config.read(user_config)
    except IOError as e:
        raise BiteError(f'cannot load config file {repr(e.filename)}: {e.strerror}')

    connection = config.defaults().get('connection', None)
    if connection is not None:
        config.remove_option('DEFAULT', 'connection')

    return config, connection


def service_files(connection=None):
    """Return iterator of service files optionally matching a given connection name."""
    for service_dir in (os.path.join(const.DATA_PATH, 'services'),
                        os.path.join(const.USER_DATA_PATH, 'services')):
        for root, _, files in os.walk(service_dir):
            for config_file in files:
                if connection is None or config_file == connection:
                    yield os.path.join(root, config_file)


def load_service_files(connection=None, config=None):
    """Load service specific configuration files."""
    config = config if config is not None else configparser.ConfigParser()

    for config_file in service_files(connection):
        try:
            with open(config_file) as f:
                config.read_file(f)
        except IOError as e:
            raise BiteError(f'cannot load config file {repr(e.filename)}: {e.strerror}')

    return config


def load_full_config():
    """Create a config object loaded with all known configuration files."""
    config, connection = load_config()
    return load_service_files(config=config)


def get_config(args, parser):
    """Load various config files for a selected connection/service."""
    config, connection = load_config()
    settings = {}

    if args.service is None or args.base is None:
        # command line connection option overrides config if it exists
        if args.connection is not None:
            connection = args.connection
        else:
            settings['connection'] = connection
        if not any ((args.service, args.base)) and connection is None:
            raise BiteError('no connection specified and no default connection set')

    # Load system connection settings and then user connection settings --
    # later settings override earlier ones. Note that only the service config
    # files matching the name of the selected connection are loaded.
    load_service_files(connection, config)

    if connection is not None:
        for config_file in service_files(connection):
            try:
                with open(config_file) as f:
                    config.read_file(f)
            except IOError as e:
                raise BiteError(f'cannot load config file {repr(e.filename)}: {e.strerror}')

    if connection:
        if not config.has_section(connection):
            parser.error(f'unknown connection: {repr(connection)}')
        else:
            settings['base'] = config.get(connection, 'base', fallback=None)
            settings['service'] = config.get(connection, 'service', fallback=None)

    # load alias files
    aliases = configparser.ConfigParser(interpolation=BiteInterpolation())
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

    return settings, config, aliases
