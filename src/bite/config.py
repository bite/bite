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


def get_config(args, parser):
    config = configparser.ConfigParser()
    aliases = configparser.ConfigParser(interpolation=BiteInterpolation())
    settings = {}

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
            settings['connection'] = args.connection
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

    if args.connection:
        if not config.has_section(args.connection):
            parser.error(f'unknown connection: {repr(args.connection)}')
        else:
            settings['base'] = config.get(args.connection, 'base', fallback=None)
            settings['service'] = config.get(args.connection, 'service', fallback=None)

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

    return settings, config, aliases
