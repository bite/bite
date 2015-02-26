import configparser
import os
import shlex
import subprocess
import sys

from bite.config import get_config_option, get_matching_options, set_config_option, BiteInterpolation, parse_config
from bite.utils import confirm

def save_alias(args, value):
    if args.connection is not None:
        section = args.connection
    else:
        section = 'default'

    exists = False
    try:
        alias_cmd = args.config[section]['alias'][args.alias]
        print(' ! Alias "{}" already exists. '.format(args.alias), end='')
        if confirm('Overwrite it?'):
            exists = True
        else:
            return
    except KeyError:
        pass

    set_config_option(args.config, section, option=option,
                        value=value, exists=exists)

def list_aliases(args):
    regex = r'^alias-.*$'
    aliases = []

    for section in [args.connection, 'default']:
        aliases.extend(get_matching_options(args.config, section, regex))

    for name, value in aliases:
        print('{}: {}'.format(name.split('-', 1)[1], value))

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

    parser = parse_config('aliases')

    sections = []
    if args.connection is not None:
        sections.append(args.connection)
    sections.append('default')

    for section in sections:
        try:
            alias_cmd = parser[section][alias_name].strip()
            break
        except KeyError:
            alias_cmd = None
        except Exception as e:
            # TODO: catch more specific exceptions and show more specific errors here
            raise

    if alias_cmd is None:
        return unparsed_args

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
