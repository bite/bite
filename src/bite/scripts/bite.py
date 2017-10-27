"""bug, issue, and ticket extraction tool

A command line tool for interacting with bugs, issues, and tickets from various
trackers in different manners.
"""

import argparse
from importlib import import_module
import os
import sys

from .. import SERVICES
from ..argparser import ArgumentParser, parse_file
from ..exceptions import BiteError, CliError, RequestError


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
single_auth.add_argument('--auth-file',
    help='load/save auth token using specified file')
auth.add_argument('--passwordcmd',
    help='password command to evaluate authentication (overrides -p/--password)')

connect = argparser.add_argument_group('Connection')
connect.add_argument('-b', '--base',
    help='base URL of service')
connect.add_argument('-s', '--service',
    help='supported services: {}'.format(', '.join(SERVICES)))
connect.add_argument('-c', '--connection',
    help='use a configured connection')

# stub for service specific arguments
service = argparser.add_argument_group('Service')

subparsers = argparser.add_subparsers(help='help for subcommands')
ls = subparsers.add_parser('ls', description='list various config info')
ls.add_argument(
    'item', choices=('aliases', 'connections', 'services'),
    help='items to list')

cache = subparsers.add_parser('cache', description='various cache related options')
cache_opts = cache.add_argument_group('Cache options')
cache_opts.add_argument('--update', action='store_true', help='update various data caches')
cache_opts.add_argument('--remove', action='store_true', help='remove various data caches')


def get_module(service_name, module_name, **kw):
    module_name = '{}.{}'.format(module_name, service_name.replace('-', '.'))
    klass_name = ''.join([s.capitalize() for s in service_name.split('-')])
    klass = getattr(import_module(module_name), klass_name)
    return klass(**kw)

def get_client(options):
    args = vars(options)
    fcn_args = args.pop('fcn_args')
    service_name = args['service']
    service = get_module(service_name, module_name='bite.services', **args)
    args['service'] = service
    client = get_module(service_name, module_name='bite.cli', **args)
    return client, fcn_args


@ls.bind_main_func
def _ls(options, out, err):
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


@cache.bind_main_func
def _cache(options, out, error):
    try:
        client, fcn_args = get_client(options)
        client.cache_config(**fcn_args)
    except (CliError, BiteError, RequestError) as e:
        msg = e.message if options.verbose else str(e)
        err.write('bite cache: error: {}'.format(msg))
        return 1

    return 0


@argparser.bind_final_check
def _validate_args(parser, namespace):
    if namespace.auth_file is not None:
        namespace.auth_file = os.path.abspath(namespace.auth_file)


@argparser.bind_main_func
def main(options, out, err):
    try:
        client, fcn_args = get_client(options)
        cmd = getattr(client, fcn_args.pop('fcn'))
        cmd(**fcn_args)
    except (CliError, BiteError, RequestError) as e:
        msg = e.message if options.verbose else str(e)
        err.write('bite: error: {}'.format(msg))
        return 1

    return 0
