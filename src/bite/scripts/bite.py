"""bug, issue, and ticket extraction tool

A command line tool for interacting with bugs, issues, and tickets from various
trackers in different manners.
"""

import argparse
import concurrent.futures
from functools import partial
from importlib import import_module
import os
import sys

from .. import const
from ..argparser import ArgumentParser, parse_file, override_attr
from ..exceptions import BiteError, CliError, RequestError


argparser = ArgumentParser(
    description=__doc__, script=(__file__, __name__))

options = argparser.add_argument_group('Options')
options.add_argument('-i', '--input',
    type=argparse.FileType('r'),
    action=parse_file,
    help='read data from an input file')
options.add_argument('--config-file',
    help='read an alternate configuration file')
options.add_argument('--columns',
    type=int,
    action=partial(override_attr, 'bite.const.COLUMNS'),
    help='maximum number of columns output should use')
options.add_argument('--suffix',
    help='domain suffix to strip or add when displaying or searching '
         '(e.g. "@domain.com")')

connect = argparser.add_argument_group('Connection')
connect.add_argument('-k', '--insecure',
    action='store_false',
    dest='verify',
    help='skip SSL certificate verification')
connect.add_argument('-n', '--dry-run',
    action='store_true',
    help='do everything except requesting or sending data')
connect.add_argument('--timeout',
    type=int,
    metavar='SECONDS',
    help='amount of time to wait before timing out requests (defaults to 30 seconds)')

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

service = argparser.add_argument_group('Service')
service.add_argument('-b', '--base',
    help='base URL of service')
service.add_argument('-s', '--service',
    help='service type')
service.add_argument('-c', '--connection',
    help='use a configured connection')

# stub for service specific arguments
service = argparser.add_argument_group('Service')

subparsers = argparser.add_subparsers(help='help for subcommands')
ls = subparsers.add_parser('ls', description='list various config info')
ls.add_argument(
    'item', choices=('aliases', 'connections', 'services'),
    help='items to list')

cache = subparsers.add_parser('cache', description='various cache related options')
cache.add_argument(
    'connections', nargs='*', help='connection cache(s) to update')
cache_opts = cache.add_argument_group('Cache options')
cache_opts.add_argument(
    '-u', '--update', action='store_true', help='update various data caches')
cache_opts.add_argument(
    '-r', '--remove', action='store_true', help='remove various data caches')


def get_client(args):
    if not isinstance(args, dict):
        args = vars(args)
    fcn_args = args.pop('fcn_args')
    service_name = args['service']
    mod_name, cls_name = const.SERVICES[service_name].rsplit('.', 1)
    service = getattr(import_module(mod_name), cls_name)(**args)
    args['service'] = service
    mod_name, cls_name = const.CLIENTS[service_name].rsplit('.', 1)
    client = getattr(import_module(mod_name), cls_name)(**args)
    return client, fcn_args


@ls.bind_main_func
def _ls(options, out, err):
    if options.item == 'aliases':
        for section in (options.aliases.default_section, options.connection):
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
        out.write('\n'.join(sorted(const.SERVICES)))

    return 0


@cache.bind_final_check
def _validate_args(parser, namespace):
    if not namespace.update and not namespace.remove:
        cache.error('either -u/--update or -r/--remove must be specified')


@cache.bind_main_func
def _cache(options, out, err):
    connections = options.pop('connections')
    if not connections:
        connections = [options.connection]
    elif connections == ['all']:
        connections = options.config.sections()

    def _cache_update(options, connection):
        service = options.config.get(connection, 'service', fallback=None)
        base = options.config.get(connection, 'base', fallback=None)
        if service is None or base is None:
            return 1
        options.connection = connection
        options.service = service
        options.base = base
        client, fcn_args = get_client(dict(vars(options)))
        try:
            client.cache_config(**fcn_args)
        except RequestError as e:
            err.write('failed updating cached data: {}: {}'.format(connection, str(e)))
            return 1
        except (CliError, BiteError) as e:
            msg = e.message if options.verbose else str(e)
            err.write('bite cache: error: {}'.format(msg))
            return 1
        return 0

    # run all cache updates in parallel
    if len(connections) > 1:
        options.quiet = True
    options.skip_auth = True
    ret = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(connections)) as executor:
        future_to_c = {executor.submit(_cache_update, options, c): c for c in connections}
        for future in concurrent.futures.as_completed(future_to_c):
            ret.append(future.result())
    return int(any(ret))


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
