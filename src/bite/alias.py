import configparser
import os
import re
import shlex
import subprocess
import sys

from snakeoil.demandload import demandload

from .exceptions import BiteError

demandload('bite:const')


class ConfigInterpolationError(configparser.InterpolationError):
    pass


class BiteInterpolation(configparser.ExtendedInterpolation):
    """Modified version of ExtendedInterpolation.

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
                orig_rest = rest
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
                        # try to pull value from config
                        if path[0] == 'CONFIG':
                            if parser.config_opts is not None:
                                try:
                                    v = parser.config_opts[path[1]]
                                except KeyError:
                                    msg = (
                                        f"{option}: {section} config section doesn't contain "
                                        f"{path[1]!r} (from config lookup '%{{{':'.join(path)}}}')")
                                    raise configparser.InterpolationError(option, section, msg)
                            elif not parser.raw:
                                msg = (
                                    f"skipping alias {option!r} since config options "
                                    f"aren't available to expand: {orig_rest!r}")
                                raise ConfigInterpolationError(option, section, msg)
                            else:
                                # skipping config interpolation since we don't have config opts
                                accum.append(orig_rest)
                                continue
                        else:
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


class AliasConfigParser(configparser.ConfigParser):
    """Alias config parser using our customized interpolation."""

    def __init__(self, config_opts, *args, **kwargs):
        interpolation = BiteInterpolation(config_opts=config_opts)
        super().__init__(*args, interpolation=interpolation, **kwargs)


def load_aliases(config_opts=None):
    """Create a config object loaded with alias file info."""
    if config_opts is not None:
        # load aliases with custom interpolation
        aliases = AliasConfigParser(config_opts=config_opts)
    else:
        # load aliases with no interpolation
        aliases = configparser.ConfigParser(interpolation=configparser.Interpolation())

    system_aliases = os.path.join(const.CONFIG_PATH, 'aliases')
    user_aliases = os.path.join(const.USER_CONFIG_PATH, 'aliases')

    try:
        with open(system_aliases) as f:
            aliases.read_file(f)
        aliases.read(user_aliases)
    except IOError as e:
        raise BiteError(f'cannot load aliases file {e.filename!r}: {e.strerror}')
    except (configparser.DuplicateSectionError, configparser.DuplicateOptionError) as e:
        raise BiteError(e)

    return aliases


def shell_split(string):
    lex = shlex.shlex(string)
    lex.whitespace_split = True
    return list(lex)


def get_alias(args, section, alias):
    value = args.config[section]['alias'][alias]
    if value[0] == '$':
        value = value[1:]
    return value


def get_sections(connection, service_name):
    """Generator for alias section precendence.

    connection -> full service name -> versioned service -> generic service

    Note that service sections use headers of the form: [:service:],
    e.g. [:bugzilla:] for a generic service
         [:bugzilla5.0:] for a version specific section
         [:bugzilla5.0-jsonrpc:] for a full service name section
    """
    if connection is not None:
        yield connection
    if service_name is not None:
        yield f":{service_name}:"
        service_versioned = service_name.split('-')[0]
        if service_versioned != service_name:
            yield f":{service_versioned}:"
            service_match = re.match(r'([a-z]+)[\d.]+', service_versioned)
            if service_match:
                yield f":{service_match.group(1)}:"


def substitute_alias(config_opts, unparsed_args, connection=None, service_name=None):
    # load alias files
    aliases = load_aliases(config_opts)

    alias_name = unparsed_args[0]
    extra_cmds = unparsed_args[1:]

    # first check for connection specific aliases, then service specific aliases
    for section in get_sections(connection, service_name):
        if aliases.has_section(section):
            try:
                alias_cmd = aliases.get(section, alias_name, fallback=None)
            except configparser.InterpolationError as e:
                raise BiteError(f'failed parsing alias: {e}')
            if alias_cmd is not None:
                break
    else:
        # finally fallback to checking global aliases
        alias_cmd = aliases.defaults().get(alias_name, None)
        if alias_cmd is None:
            return unparsed_args

    alias_cmd = alias_cmd.strip()

    if alias_cmd[0] == '!':
        run_shell_cmd(alias_cmd[1:] + ' ' + ' '.join(shlex.quote(s) for s in extra_cmds))

    params = shell_split(alias_cmd)
    params.extend(extra_cmds)
    return params


def run_shell_cmd(cmd):
    # TODO: handle failures, errors, and keyboard interrupts better
    p = subprocess.Popen(cmd, shell=True)
    p.communicate()
    sys.exit(p.returncode)
