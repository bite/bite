"""bug, issue, and ticket extraction tool

A command line tool for interacting with bugs, issues, and tickets from various
trackers in different manners.
"""

import argparse
import concurrent.futures
from functools import partial
import os

from snakeoil.demandload import demandload

from ..argparser import ArgumentParser, parse_file, override_attr
from ..base import get_service_cls
from ..alias import Aliases
from ..client import Cli
from ..config import Config
from ..exceptions import RequestError

demandload('bite:const')


argparser = ArgumentParser(
    description=__doc__, script=(__file__, __name__))

config_opts = argparser.add_argument_group('Config options')
config_opts.add_argument(
    '-c', '--connection',
    help='use a configured connection')
config_opts.add_argument(
    '--config-file',
    help='read an alternate configuration file')

service_opts = argparser.add_argument_group('Service options')
service_opts.add_argument(
    '-b', '--base',
    help='base URL of service')
service_opts.add_argument(
    '-s', '--service',
    help='service type')

argparser.add_argument(
    '-i', '--input',
    type=argparse.FileType('r'), action=parse_file,
    help='read data from an input file')
argparser.add_argument(
    '--columns', type=int,
    action=partial(override_attr, 'bite.const', 'COLUMNS'),
    help='maximum number of columns output should use')
argparser.add_argument(
    '--suffix',
    help='domain suffix to strip or add when displaying or searching '
         '(e.g. "@domain.com")')

connect_opts = argparser.add_argument_group('Connection options')
connect_opts.add_argument(
    '-k', '--insecure', action='store_false', dest='verify',
    help='skip SSL certificate verification')
connect_opts.add_argument(
    '-C', '--concurrent', type=int,
    help='maximum number of allowed concurrent requests to a service')
connect_opts.add_argument(
    '--timeout', type=float, metavar='SECONDS',
    help='amount of time to wait before timing out requests (defaults to 30 seconds)')

auth_opts = argparser.add_argument_group('Authentication options')
single_auth_opts = auth_opts.add_mutually_exclusive_group()
single_auth_opts.add_argument(
    '-S', '--skip-auth', action='store_true',
    help='skip authenticating to the specified service')
single_auth_opts.add_argument(
    '-u', '--user',
    help='username for authentication')
auth_opts.add_argument(
    '-p', '--password',
    help='password for authentication')
single_auth_opts.add_argument(
    '-a', '--auth-token',
    help='use the specified token for authentication')
single_auth_opts.add_argument(
    '--auth-file',
    help='load/save auth token using specified file')
auth_opts.add_argument(
    '--passwordcmd',
    help='command to run for password')

# stub for service specific arguments
service_specific_opts = argparser.add_argument_group('Service specific options')

subparsers = argparser.add_subparsers()
aliases = subparsers.add_parser(
    'aliases', description='view available aliases')
connections = subparsers.add_parser(
    'connections', description='view available connections')
connections.add_argument(
    '-s', '--service', help='connections using matching service')
services = subparsers.add_parser(
    'services', description='view available services')

cache = subparsers.add_parser(
    'cache', description='various cache related options')
cache.add_argument(
    'connections', nargs='*', metavar='connection',
    help='connection cache(s) to update')
cache_opts = cache.add_argument_group('Cache options')
cache_opts.add_argument(
    '-u', '--update', action='store_true',
    help='update various data caches')
cache_opts.add_argument(
    '-r', '--remove', action='store_true',
    help='remove various data caches')


def get_cli(args):
    if not isinstance(args, dict):
        args = vars(args)
    fcn_args = args.pop('fcn_args')

    # fcn settings that override client level args
    for attr in ('verbosity', 'debug'):
        val = fcn_args.pop(attr, None)
        if val:
            args[attr] = val

    service_name = args['service']._service
    client = get_service_cls(
        service_name, const.CLIENTS, fallbacks=(True, Cli))(**args)
    return client, fcn_args


@aliases.bind_main_func
def _aliases(options, out, err):
    aliases = Aliases(raw=True)
    section = options.connection if options.connection else 'DEFAULT'
    for name, value in aliases.items(section):
        if options.verbosity > 0:
            out.write(f'{name}: {value}')
        else:
            out.write(name)
    return 0


@connections.bind_main_func
def _connections(options, out, err):
    # load all service connections
    config = Config(connection=None)
    service = options.service if options.service is not None else ''
    connections = (
        x for x in config.sections()
        if config[x]['service'].startswith(service))
    for connection in sorted(connections):
        if options.verbosity > 0:
            out.write(f'[{connection}]')
            for (name, value) in config.items(connection):
                out.write(f'  {name}: {value}')
        else:
            out.write(connection)
    return 0


@services.bind_main_func
def _services(options, out, err):
    out.write('\n'.join(sorted(const.SERVICES)))
    return 0


@cache.bind_final_check
def _cache_validate_args(parser, namespace):
    if not namespace.update and not namespace.remove:
        cache.error('either -u/--update or -r/--remove must be specified')


@cache.bind_main_func
def _cache(options, out, err):
    # load all service connections
    config = Config(connection=None)
    connections = options.pop('connections')
    if not connections:
        connections = [options.connection]
    elif connections == ['all']:
        connections = config.sections()

    def _cache_update(options, connection):
        service = config.get(connection, 'service', fallback=None)
        base = config.get(connection, 'base', fallback=None)
        if service is None or base is None:
            return 1
        options.connection = connection
        options.base = base
        args = vars(options)
        options.service = get_service_cls(service, const.SERVICES)(**args)
        client = get_service_cls(args['service'], const.CLIENTS, fallbacks=(Cli,))(**args)
        try:
            client.cache(**args)
        except RequestError as e:
            err.write(f'failed updating cached data: {connection}: {e}')
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
    client, fcn_args = get_cli(options)
    cmd = getattr(client, fcn_args.pop('fcn'))
    cmd(**fcn_args)
    return 0
