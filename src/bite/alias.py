import configparser
import os
import re
import shlex
import subprocess
import sys

from snakeoil.demandload import demandload

from . import service_classes
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

    def __init__(self, *args, config_opts=None, raw=False, **kwargs):
        self.config_opts = config_opts
        self.raw = raw
        interpolation = BiteInterpolation()
        super().__init__(*args, interpolation=interpolation, **kwargs)


class Aliases(object):

    def __init__(self, path=None, config_opts=None, **kw):
        self._aliases = AliasConfigParser(config_opts=config_opts, **kw)

        system_aliases = os.path.join(const.CONFIG_PATH, 'aliases')
        user_aliases = os.path.join(const.USER_CONFIG_PATH, 'aliases')

        paths = [(system_aliases, True), (user_aliases, False)]
        if path: paths.append((path, True))

        for path, force in paths:
            self.load(path, force)

    def load(self, path, force=False):
        """Create a config object loaded with alias file info."""
        try:
            if force:
                with open(path) as f:
                    self._aliases.read_file(f)
            else:
                self._aliases.read(path)
        except IOError as e:
            raise BiteError(f'cannot load aliases file {e.filename!r}: {e.strerror}')
        except (configparser.DuplicateSectionError, configparser.DuplicateOptionError) as e:
            raise BiteError(e)

    def substitute(self, unparsed_args, *,
                   config=None, config_opts=None, connection=None,
                   service_name=None, debug=False):
        # load alias files
        if config_opts is not None:
            self._aliases.config_opts = config_opts

        alias_name = unparsed_args[0]
        remaining_args = unparsed_args[1:]

        # sections to check in order for matching aliases
        sections = []
        if connection is not None:
            sections.append(connection)

        # load aliases from connection config if they exist
        if config is not None and config.has_section(':alias:'):
            d = {'alias': dict(config.items(':alias:'))}
            self._aliases.read_dict(d)
            sections.append('alias')

        sections.extend(self.get_sections(service_name))

        # first check for connection specific aliases, then service specific aliases
        for section in sections:
            if self._aliases.has_section(section):
                try:
                    alias_cmd = self._aliases.get(section, alias_name, fallback=None)
                except configparser.InterpolationError as e:
                    raise BiteError(f'failed parsing alias: {e}')
                if alias_cmd is not None:
                    break
        else:
            # finally fallback to checking global aliases
            try:
                alias_cmd = self._aliases.get(self._aliases.default_section, alias_name, fallback=None)
            except ConfigInterpolationError as e:
                alias_cmd = None
            if alias_cmd is None:
                return unparsed_args

        alias_cmd = alias_cmd.strip()
        # strip quotes if the alias starts with them
        if alias_cmd.startswith(('"', "'")):
            alias_cmd = alias_cmd.strip('"\'')

        # run '!' prefixed aliases in the system shell
        if alias_cmd.startswith('!'):
            # assumes we're running in bash or shell compatible with 'set -x'
            enable_debug = 'set -x; ' if debug else ''
            stderr = None if debug else subprocess.PIPE
            cmd_str = (
                f"{enable_debug}{alias_cmd[1:]} "
                f"{' '.join(shlex.quote(s) for s in remaining_args)}")
            p = subprocess.run(cmd_str, stderr=stderr, shell=True)
            if not debug:
                try:
                    p.check_returncode()
                except subprocess.CalledProcessError as e:
                    stderr_str = p.stderr.decode().strip()
                    if stderr_str.startswith('/bin/sh: '):
                        stderr_lines = '\n'.join(
                            f'  {x}' for x in stderr_str.split('\n'))
                        msg = f"failed running {alias_name!r}:\n{stderr_lines}"
                        raise BiteError(msg=msg)
            sys.exit(p.returncode)

        return shell_split(alias_cmd) + remaining_args

    @staticmethod
    def get_sections(service_name):
        """Generator for alias section precendence.

        full service name -> versioned service -> generic service

        Note that service sections use headers of the form: [:service:],
        e.g. [:bugzilla:] for a generic service
            [:bugzilla5.0:] for a version specific section
            [:bugzilla5.0-jsonrpc:] for a full service name section
        """
        for cls in service_classes(service_name):
            yield f":{cls}:"

    def items(self, section):
        return self._aliases.items(section)


def shell_split(s):
    lex = shlex.shlex(s)
    lex.whitespace_split = True
    return list(lex)
