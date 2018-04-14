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
from ..config import load_full_config
from ..exceptions import RequestError

demandload('bite:get_service_cls,const')


config_opts_parser = ArgumentParser(suppress=True)
config_opts = config_opts_parser.add_argument_group('Config options')
config_opts.add_argument(
    '-c', '--connection',
    help='use a configured connection')
config_opts.add_argument(
    '--config-file',
    help='read an alternate configuration file')

service_opts = config_opts_parser.add_argument_group('Service options')
service_opts.add_argument(
    '-b', '--base',
    help='base URL of service')
service_opts.add_argument(
    '-s', '--service',
    help='service type')

argparser = ArgumentParser(
    description=__doc__, script=(__file__, __name__),
    parents=(config_opts_parser,))

argparser.add_argument(
    '-i', '--input',
    type=argparse.FileType('r'), action=parse_file,
    help='read data from an input file')
argparser.add_argument(
    '--columns', type=int,
    action=partial(override_attr, 'bite.const.COLUMNS'),
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
    '-n', '--dry-run', action='store_true',
    help='do everything except requesting or sending data')
connect_opts.add_argument(
    '-C', '--concurrent', type=int,
    help='maximum number of allowed concurrent requests to a service')
connect_opts.add_argument(
    '--timeout', type=int, metavar='SECONDS',
    help='amount of time to wait before timing out requests (defaults to 30 seconds)')

auth_opts = argparser.add_argument_group('Authentication options')
single_auth_opts = auth_opts.add_mutually_exclusive_group()
single_auth_opts.add_argument(
    '-S', '--skip-auth', action='store_true',
    help='skip authenticating to the specified service')
single_auth_opts.add_argument(
    '-u', '--user',
    help='username for authentication')
auth_opts.add_argument('-p', '--password',
    help='password for authentication')
single_auth_opts.add_argument('-a', '--auth-token',
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
ls = subparsers.add_parser('ls', description='list various config info')
ls.add_argument(
    'item', choices=('aliases', 'connections', 'services'),
    help='items to list')

cache = subparsers.add_parser('cache', description='various cache related options')
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
    client = get_service_cls(args['service'], const.CLIENTS)(**args)
    return client, fcn_args


@ls.bind_main_func
def _ls(options, out, err):
    if options.item == 'aliases':
        for section in (options.aliases.default_section, options.connection):
            for name, value in options.aliases.items(section):
                if options.verbose:
                    out.write(f'{name}: {value}')
                else:
                    out.write(name)
    elif options.item == 'connections':
        config = load_full_config()
        for connection in sorted(config.sections()):
            if options.verbose:
                out.write(f'[{connection}]')
                for (name, value) in config.items(connection):
                    out.write(f'  {name}: {value}')
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
    config = load_full_config()
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
        options.service = get_service_cls(service, const.SERVICES)(**vars(options))
        client, fcn_args = get_cli(dict(vars(options)))
        try:
            client.cache(**fcn_args)
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
