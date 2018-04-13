import configparser
import re
import shlex
import subprocess
import sys


class BiteInterpolation(configparser.ExtendedInterpolation):
    """Modified version of ExtendedInterpolation.

    Uses %{option} for options local to the current section or default section
    and %{section:option} for options in different sections.
    """

    _KEYCRE = re.compile(r"\%\{([^}]+)\}")

    def __init__(self, config_opts):
        self.config_opts = config_opts

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
                        # try to pull value from config
                        if path[0] == 'CONFIG':
                            v = self.config_opts[path[1]]
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

    def __init__(self, config_opts, *args, **kwargs):
        interpolation = BiteInterpolation(config_opts=config_opts)
        super().__init__(*args, interpolation=interpolation, **kwargs)


def shell_split(string):
    lex = shlex.shlex(string)
    lex.whitespace_split = True
    return list(lex)


#def inner_alias(args, section, inner_alias):
#    # TODO: check for arguments
#    try:
#        alias = args.config[section]['alias'][inner_alias[1:]]
#    except KeyError:
#        raise RuntimeError('Unknown alias "{}"'.format(inner_alias[1:]))
#    if alias_list[i][0] == '$':
#        alias_list[i] = alias_list[i][1:]


def get_alias(args, section, alias):
    value = args.config[section]['alias'][alias]
    if value[0] == '$':
        value = value[1:]
    return value


def substitute_alias(connection, service_type, aliases, unparsed_args):
    alias_name = unparsed_args[0]
    extra_cmds = unparsed_args[1:]

    # service sections use headers of the form:
    # {:service:}, e.g. {:bugzilla:}
    service_section = f":{service_type}:"

    for section in (connection, service_section, aliases.default_section):
        if aliases.has_section(section):
            alias_cmd = aliases.get(section, alias_name, fallback=None)
            if alias_cmd is not None:
                break
    else:
        return unparsed_args

    alias_cmd = alias_cmd.strip()

    if alias_cmd[0] == '!':
        #print(alias_cmd[0])
        #if extra_cmds[0] == '-':
        #    import codecs
        #    sys.stdin = codecs.getreader('utf-8')(sys.stdin)
        #    if len(extra_cmds) > 1:
        #        extra_args = ' '.join(pipes.quote(s) for s in extra_cmds[1:])
        #        extra_cmds = ['{} {}'.format(s.strip(), extra_args) for s in sys.stdin.readlines() if s.strip() != '']
        #    else:
        #        extra_cmds = [s.strip() for s in sys.stdin.readlines() if s.strip() != '']
        #    sys.stdin = open('/dev/tty')
        run_shell_cmd(alias_cmd[1:] + ' ' + ' '.join(shlex.quote(s) for s in extra_cmds))

    params = shell_split(alias_cmd)
    params.extend(extra_cmds)
    return params


def run_shell_cmd(cmd):
    #print(cmd)
    # TODO: handle failures, errors, and keyboard interrupts better
    p = subprocess.Popen(cmd, shell=True)
    p.communicate()
    sys.exit(p.returncode)
