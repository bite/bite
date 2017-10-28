import shlex
import subprocess
import sys


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

def substitute_alias(args, unparsed_args):
    alias_name = unparsed_args[0]
    extra_cmds = unparsed_args[1:]

    if args.connection is not None and args.aliases.has_section(args.connection):
        section = args.connection
    else:
        section = args.aliases.default_section
    alias_cmd = args.aliases.get(section, alias_name, fallback=None)

    if alias_cmd is None:
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
