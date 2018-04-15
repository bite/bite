import configparser
import os

from snakeoil.demandload import demandload

from .alias import AliasConfigParser
from .exceptions import BiteError

demandload('bite:const')


def load_config(config=None, config_file=None):
    """Load system and user configuration files."""
    config = config if config is not None else configparser.ConfigParser()

    # config file specified on the command line overrides the system config
    if config_file is not None:
        system_config = config_file
    else:
        system_config = os.path.join(const.CONFIG_PATH, 'bite.conf')
    user_config = os.path.join(const.USER_CONFIG_PATH, 'bite.conf')

    try:
        with open(system_config) as f:
            config.read_file(f)
        config.read(user_config)
    except IOError as e:
        raise BiteError(f'cannot load config file {e.filename!r}: {e.strerror}')

    connection = config.defaults().get('connection', None)
    if connection is not None:
        config.remove_option('DEFAULT', 'connection')

    return config, connection


def service_files(connection=None):
    """Return iterator of service files optionally matching a given connection name."""
    for service_dir in (os.path.join(const.DATA_PATH, 'services'),
                        os.path.join(const.USER_DATA_PATH, 'services')):
        for root, _, files in os.walk(service_dir):
            for config_file in files:
                if connection is None or config_file == connection:
                    yield os.path.join(root, config_file)


def load_service_files(connection=None, config=None):
    """Load service specific configuration files."""
    config = config if config is not None else configparser.ConfigParser()

    for config_file in service_files(connection):
        try:
            with open(config_file) as f:
                config.read_file(f)
        except IOError as e:
            raise BiteError(f'cannot load config file {e.filename!r}: {e.strerror}')

    return config


def load_full_config(config_file=None):
    """Create a config object loaded with all known configuration files."""
    config, connection = load_config(config_file)
    return load_service_files(config=config)


def get_config(args, config_file=None):
    """Load various config files for a selected connection/service."""
    config, default_connection = load_config(config_file)

    # Fallback to using the default connection setting from the config if not
    # specified on the command line and --base/--service options are also
    # unspecified.
    if args.connection is not None:
        connection = args.connection
    elif args.base is None and args.service is None:
        args.connection = default_connection
        connection = default_connection
    else:
        connection = None

    # Load system connection settings and then user connection settings --
    # later settings override earlier ones. Note that only the service config
    # files matching the name of the selected connection are loaded.
    load_service_files(connection, config)

    if connection is not None:
        for config_file in service_files(connection):
            try:
                with open(config_file) as f:
                    config.read_file(f)
            except IOError as e:
                raise BiteError(f'cannot load config file {e.filename!r}: {e.strerror}')

    if connection:
        if not config.has_section(connection):
            raise BiteError(f'unknown connection: {connection!r}')

    # pop base and service settings from the config and add them to parsed args
    # if not already specified on the command line
    for attr in ('base', 'service'):
        if getattr(args, attr, None) is None:
            setattr(args, attr, config.get(connection, attr, fallback=None))
        config.remove_option(connection, attr)

    if connection is not None:
        config_opts = dict(config.items(connection))
    else:
        config_opts = config.defaults()

    # load alias files
    aliases = AliasConfigParser(config_opts=config_opts)
    system_aliases = os.path.join(const.CONFIG_PATH, 'aliases')
    user_aliases = os.path.join(const.USER_CONFIG_PATH, 'aliases')
    try:
        with open(system_aliases) as f:
            aliases.read_file(f)
        aliases.read(user_aliases)
    except IOError as e:
        raise BiteError(f'cannot load aliases file {e.filename!r}: {e.strerror}')
    except (configparser.DuplicateSectionError, configparser.DuplicateOptionError) as e:
        raise BiteError(e)

    return config, config_opts, aliases
