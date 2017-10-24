"""bug, issue, and ticket extraction tool

A command line tool for interacting with bugs, issues, and tickets from various
trackers in different manners.
"""

import argparse
from importlib import import_module
import os
import sys

from bite import SERVICES
from bite.argparser import ArgumentParser, parse_file
from bite.exceptions import CliError, CommandError, RequestError


argparser = ArgumentParser(
    description=__doc__, script=(__file__, __name__))

options = argparser.add_argument_group('Options')
options.add_argument('-i', '--input',
    type=argparse.FileType('r'),
    action=parse_file,
    help='read data from an input file')
options.add_argument('-k', '--insecure',
    action='store_false',
    dest='verify',
    help='skip SSL certificate verification')
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
options.add_argument('--suffix',
    help='domain suffix to strip or add when displaying or searching '
         '(e.g. "@domain.com")')
options.add_argument('--timeout',
    type=int,
    metavar='SECONDS',
    help='amount of time to wait before timing out requests')

auth = argparser.add_argument_group('Authentication')
single_auth = auth.add_mutually_exclusive_group()
single_auth.add_argument('-a', '--auth-token',
    help='use the specified token for authentication')
single_auth.add_argument('-S', '--skip-auth',
    action='store_true',
    help='skip authenticating to the specified service')
single_auth.add_argument('-u', '--user',
    help='username for authentication')
auth.add_argument('-p', '--password',
    help='password for authentication')
single_auth.add_argument('--load-auth',
    dest='authfile',
    type=argparse.FileType('r'),
    help='load auth token from file')
auth.add_argument('--passwordcmd',
    help='password command to evaluate authentication (overrides -p/--password)')

service = argparser.add_argument_group('Service')
service.add_argument('-b', '--base',
    help='base URL of service')
service.add_argument('-s', '--service',
    help='supported services: {}'.format(', '.join(SERVICES)))
service.add_argument('-c', '--connection',
    help='use a configured connection')

subparsers = argparser.add_subparsers(help='help for subcommands')
ls = subparsers.add_parser('ls', description='list various config info')
ls.add_argument(
    'item', choices=('aliases', 'connections', 'services'),
    help='items to list')

def get_service(service_name, module_name, **kw):
    module_name = '{}.{}'.format(module_name, service_name.replace('-', '.'))
    klass_name = ''.join([s.capitalize() for s in service_name.split('-')])
    klass = getattr(import_module(module_name), klass_name)
    return klass(**kw)


@ls.bind_main_func
def _ls(options, out, error):
    if options.item == 'aliases':
        for section in ('default', options.connection):
            for name, value in options.aliases.items(section):
                if options.verbose:
                    out.write('{}: {}'.format(name, value))
                else:
                    out.write(name)
    elif options.item == 'connections':
        for connection in sorted(options.config.sections()):
            if options.verbose:
                out.write('[{}]'.format(connection))
                for (name, value) in options.config.items(connection):
                    out.write('  {}: {}'.format(name, value))
            else:
                out.write(connection)
    elif options.item == 'services':
        out.write('\n'.join(sorted(SERVICES)))

    return 0


@argparser.bind_main_func
def main(options, out, err):
    try:
        args = vars(options)
        fcn_args = args.pop('fcn_args')
        service_name = args['service']
        service = get_service(service_name, module_name='bite.services', **args)
        args['service'] = service
        client = get_service(service_name, module_name='bite.cli', **args)
        cmd = getattr(client, fcn_args.pop('fcn'))
        cmd(**fcn_args)
    except (CliError, CommandError, RequestError) as e:
        # TODO: output verbose text attr from RequestError if verbose is enabled
        if options.verbose:
            msg = e.verbose()
        else:
            msg = str(e)
        err.write('bite: error: {}'.format(msg))
        return 1

    return 0
