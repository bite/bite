import argparse
import logging
import os
import re
from signal import signal, SIGPIPE, SIG_DFL, SIGINT
import sys

import bite
from bite.alias import list_aliases, save_alias, substitute_alias
from bite.argparser import ParseInitialArgs, ParseArgs, parse_file
from bite.config import get_config
from bite.exceptions import CliError, CommandError, RequestError


def make_initialparser():
    parser = ParseInitialArgs(
        add_help=False,
        epilog='use -h after a sub-command for sub-command specific help')
    parser.add_argument('-a', '--alias',
        dest='save_alias',
        help='save the specified parameters to an alias')
    parser.add_argument('-i', '--input',
        type=argparse.FileType('r'),
        action=parse_file,
        help='read data from an input file')
    parser.add_argument('-j', '--jobs',
        type=int,
        default=8,
        help='Run commands in parallel from a job pool')
    parser.add_argument('-l', '--login',
        action='store_true',
        help='force authentication to the specified service')
    parser.add_argument('-n', '--dry-run',
        action='store_true',
        help='do everything except requesting or sending data')
    parser.add_argument('-q', '--quiet',
        action='store_true',
        help='quiet mode')
    parser.add_argument('--config-file',
        help='read an alternate configuration file')
    parser.add_argument('--columns',
        type=int,
        help='maximum number of columns output should use')
    parser.add_argument('--encoding',
        help='output encoding (default: utf-8)')
    parser.add_argument('--list-aliases',
        action='store_true',
        help='list the available aliases')
    parser.add_argument('--no-verify',
        action='store_false',
        dest='verify',
        help='skip verifying SSL certificates')
    parser.add_argument('--suffix',
        help='domain suffix to strip or add when displaying or searching '
             '(e.g. "@domain.com")')
    parser.add_argument('--timeout',
        type=int,
        metavar='SECONDS',
        help='amount of time to wait before timing out requests')
    parser.add_argument('--version',
        action='version',
        help='show program version and exit',
        version='%(prog)s ' + bite.__version__)
    auth = parser.add_argument_group('Authentication')
    auth.add_argument('-u', '--user',
        help='username for authentication')
    auth.add_argument('-p', '--password',
        help='password for authentication')
    auth.add_argument('--load-cookies',
        dest='cookies',
        help='load cookies from file for authentication')
    auth.add_argument('--passwordcmd',
        help='password command to evaluate authentication')
    service = parser.add_argument_group('Service')
    service.add_argument('-b', '--base',
        help='base URL of service')
    service.add_argument('-c', '--connection',
        help='use a connection from the config file')
    service.add_argument('-s', '--service',
        help='service type: {}'.format(', '.join(bite.SERVICES)))
    return parser

def parse_args():
    initial_parser = make_initialparser()
    initial_args, unparsed_args = initial_parser.parse_known_args()

    # allow symlinks to bite to override the connection type
    if os.path.basename(sys.argv[0]) != 'bite':
        initial_args.connection = os.path.basename(sys.argv[0])

    # get settings from the config file
    get_config(initial_args, initial_parser)

    logger = logging.getLogger(__name__)
    #logger.setLevel(logging.DEBUG)

    # default to gentoo bugzilla if no service is selected
    if initial_args.base is None and initial_args.service is None:
        initial_args.base = 'https://bugs.gentoo.org/'
        initial_args.service = 'bugzilla-jsonrpc'

    if initial_args.base is None or initial_args.service is None:
        initial_parser.error('both arguments -b/--base and -s/--service are required '
                             'or must be specified in the config file for a connection')

    service_name = initial_args.service

    if initial_args.list_aliases:
        list_aliases(initial_args)
        sys.exit(0)

    # create sub-command argument parser for the specified service type
    parser = ParseArgs(parents=[initial_parser],
        epilog = 'use -h after a sub-command for sub-command specific help')
    subparsers = parser.add_subparsers(help = 'help for sub-commands')
    module_name = 'bite.args.' + service_name.replace('-', '.')

    # add any additional service specific top level commands
    try:
        maincmds = __import__(module_name, globals(), locals(), ['maincmds']).maincmds
        maincmds(parser)
    except AttributeError:
        pass

    # add sub-commands
    subcmds = __import__(module_name, globals(), locals(), ['subcmds']).subcmds
    subcmds(subparsers)

    # check if unparsed args match any aliases
    if unparsed_args:
        unparsed_args = substitute_alias(initial_args, unparsed_args)

    # save args as specified alias
    if initial_args.save_alias is not None:
        save_alias(initial_args, ' '.join(unparsed_args))

    parser.set_defaults(connection=initial_args.connection)

    if initial_args.input is not None:
        unparsed_args = substitute_args(unparsed_args, initial_args)
    else:
        initial_args, unparsed_args = initial_parser.parse_known_args(unparsed_args, initial_args)
        unparsed_args = [unparsed_args]

    fcn_args = iterate_fcn_args(parser, initial_args, unparsed_args)
    return (vars(initial_args), fcn_args)

def substitute_args(args, initial_args):
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

def iterate_fcn_args(parser, initial_args, unparsed_args):
    for uargs in unparsed_args:
        fcn_args = vars(parser.parse_args(args=uargs))
        #alias_args = {k:v for k,v in fcn_args.items() if k in initial_args.keys()
        #              and v != initial_args[k] and v is not None}
        #args = initial_args.update(alias_args)
        args = vars(initial_args)
        fcn_args = {k:v for k,v in fcn_args.items() if k not in args.keys()}
        for i in ['dry_run', 'jobs']:
            if i in args:
                fcn_args[i] = args[i]
        yield fcn_args

def get_service(service_name, module_name, **kw):
    module_name = '{}.{}'.format(module_name, service_name.replace('-', '.'))
    klass_name = ''.join([s.capitalize() for s in service_name.split('-')])
    module = __import__(module_name, globals(), locals(), [klass_name])
    klass = getattr(module, klass_name)
    return klass(**kw)

def main(args):
    signal(SIGPIPE, SIG_DFL)
    signal(SIGINT, SIG_DFL)

    try:
        initial_args, args_list = parse_args()
        service_name = initial_args['service']
        service = get_service(service_name, module_name='bite.services', **initial_args)
        initial_args['service'] = service
        client = get_service(service_name, module_name='bite.cli', **initial_args)
        for args in args_list:
            cmd = getattr(client, args['fcn'])
            cmd(**args)

        #client.run(args, **initial_args)

    except (CliError, CommandError, RequestError) as e:
        print('bite: error: {}'.format(e))
        sys.exit(1)
    except:
        raise
