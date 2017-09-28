"""bug and issue extraction tool

A command line tool for interacting with bugs and issues from various trackers.
"""

import argparse
import logging
import os
import re
import sys

import bite
from bite.alias import list_aliases, save_alias, substitute_alias
from bite.argparser import ParseInitialArgs, ParseArgs, parse_file
from bite.config import get_config
from bite.exceptions import CliError, CommandError, RequestError

from snakeoil.cli import arghparse

initial_parser = ParseInitialArgs(add_help=False)
options = initial_parser.add_argument_group('Options')
options.add_argument('-a', '--alias',
    dest='save_alias',
    help='save the specified parameters to an alias')
options.add_argument('-i', '--input',
    type=argparse.FileType('r'),
    action=parse_file,
    help='read data from an input file')
options.add_argument('-j', '--jobs',
    type=int,
    default=8,
    help='Run commands in parallel from a job pool')
options.add_argument('-l', '--login',
    action='store_true',
    help='force authentication to the specified service')
options.add_argument('-n', '--dry-run',
    action='store_true',
    help='do everything except requesting or sending data')
options.add_argument('--config-file',
    help='read an alternate configuration file')
options.add_argument('--columns',
    type=int,
    help='maximum number of columns output should use')
options.add_argument('--encoding',
    help='output encoding (default: utf-8)')
options.add_argument('--list-aliases',
    action='store_true',
    help='list the available aliases')
options.add_argument('--no-verify',
    action='store_false',
    dest='verify',
    help='skip verifying SSL certificates')
options.add_argument('--suffix',
    help='domain suffix to strip or add when displaying or searching '
            '(e.g. "@domain.com")')
options.add_argument('--timeout',
    type=int,
    metavar='SECONDS',
    help='amount of time to wait before timing out requests')

auth = initial_parser.add_argument_group('Authentication')
auth.add_argument('-u', '--user',
    help='username for authentication')
auth.add_argument('-p', '--password',
    help='password for authentication')
auth.add_argument('--load-cookies',
    dest='cookies',
    help='load cookies from file for authentication')
auth.add_argument('--passwordcmd',
    help='password command to evaluate authentication')

service = initial_parser.add_argument_group('Service')
service.add_argument('-b', '--base',
    help='base URL of service')
service.add_argument('-c', '--connection',
    help='use a connection from the config file')
service.add_argument('-s', '--service',
    help='service type: {}'.format(', '.join(bite.SERVICES)))


class ArgumentParser(arghparse.ArgumentParser):

    def parse_args(self, args=None, namespace=None):
        if namespace is None:
            namespace = arghparse.Namespace()

        initial_args, unparsed_args = initial_parser.parse_known_args(args, namespace)

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
            argparser.error('both arguments -b/--base and -s/--service are required '
                            'or must be specified in the config file for a connection')

        service_name = initial_args.service

        if initial_args.list_aliases:
            list_aliases(initial_args)
            sys.exit(0)

        if not unparsed_args:
            argparser.error('a subcommand must be selected')

        # create subcommand argument parser for the specified service type
        subcmd_parser = ParseArgs(parents=[initial_parser],
            epilog = 'use -h after a subcommand for subcommand specific help')
        subparsers = subcmd_parser.add_subparsers(help = 'help for subcommands')
        module_name = 'bite.args.' + service_name.replace('-', '.')

        # add any additional service specific top level commands
        try:
            maincmds = __import__(module_name, globals(), locals(), ['maincmds']).maincmds
            maincmds(subcmdparser)
        except AttributeError:
            pass

        # add subcommands
        subcmds = __import__(module_name, globals(), locals(), ['subcmds']).subcmds
        subcmds(subparsers)

        # check if unparsed args match any aliases
        if unparsed_args:
            unparsed_args = substitute_alias(initial_args, unparsed_args)

        # save args as specified alias
        if initial_args.save_alias is not None:
            save_alias(initial_args, ' '.join(unparsed_args))

        subcmd_parser.set_defaults(connection=initial_args.connection)

        if initial_args.input is not None:
            unparsed_args = substitute_args(unparsed_args, initial_args)
        else:
            initial_args, unparsed_args = initial_parser.parse_known_args(unparsed_args, initial_args)
            unparsed_args = [unparsed_args]

        initial_args.fcn_args = iterate_fcn_args(subcmd_parser, initial_args, unparsed_args)
        return super().parse_args('', initial_args)

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


argparser = ArgumentParser(
    description=__doc__, script=(__file__, __name__), parents=(initial_parser,))

@argparser.bind_main_func
def main(options, out, err):
    try:
        args = vars(options)
        service_name = args['service']
        service = get_service(service_name, module_name='bite.services', **args)
        args['service'] = service
        client = get_service(service_name, module_name='bite.cli', **args)
        for fcn_args in options.fcn_args:
            cmd = getattr(client, fcn_args['fcn'])
            cmd(**fcn_args)
        #client.run(args, **initial_args)
    except (CliError, CommandError, RequestError) as e:
        # TODO: output verbose text attr from RequestError if verbose is enabled
        if options.verbose:
            msg = e.verbose()
        else:
            msg = str(e)
        err.write('bite: error: {}'.format(msg))
        sys.exit(1)
