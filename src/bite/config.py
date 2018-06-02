import re
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap
import shlex
import os

from snakeoil.demandload import demandload

from . import service_classes
from .exceptions import BiteError
from .utils import run_shell_cmd, shell_split

demandload('bite:const')


class Config(object):

    def __init__(self, path=None):
        self._yaml = YAML()
        self._config = CommentedMap()

        # load system config
        system_config = os.path.join(const.CONFIG_PATH, 'bite.yml')
        self.load(system_config)

        # optionally load user config, forcibly load if overridden
        if path is None:
            user_config = os.path.join(const.USER_CONFIG_PATH, 'bite.yml')
            if os.path.exists(user_config):
                self.load(user_config)
        else:
            self.load(path)

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

        return config, config_opts

    def load(self, path):
        """Load config files."""
        try:
            with open(path) as f:
                self._config.update(self._yaml.load(f.read()))
        except IOError as e:
            raise BiteError(f'cannot load config file {e.filename!r}: {e.strerror}')

    def load_all(self, config_file=None):
        """Create a config object loaded with all known configuration files."""
        config, connection = self.load(config_file)
        return self.load_service_files(config=config)

    @staticmethod
    def service_files(connection=None, user_dir=True):
        """Return iterator of service files optionally matching a given connection name."""
        dirs = [os.path.join(const.DATA_PATH, 'services')]
        if user_dir:
            dirs.append(os.path.join(const.USER_DATA_PATH, 'services'))

        for service_dir in dirs:
            for root, _, files in os.walk(service_dir):
                for config_file in (x for x in files if not x.startswith('.')):
                    if connection is None or config_file.rsplit('.')[0] == connection:
                        yield os.path.join(root, config_file)

    def load_service(self, connection, user_dir=True):
        """Load service specific configuration files.

        Load system connection settings and then user connection settings --
        later settings override earlier ones. Note that only the service config
        files matching the name of the selected connection are loaded.
        """
        files = tuple(self.service_files(connection, user_dir=user_dir))
        if not files:
            raise BiteError(f'unknown connection: {connection!r}')

        for config_file in files:
            try:
                with open(config_file) as f:
                    self._config.update(self._yaml.load(f.read()))
            except IOError as e:
                raise BiteError(f'cannot load config file {e.filename!r}: {e.strerror}')

    def aliases(self, *, service_name, connection=None):
        """Dictionary of aliases overridden via preference."""
        # global aliases
        d = self._config.get('alias', {})
        # service aliases
        for section in (x.upper() for x in reversed(tuple(service_classes(service_name)))):
            if section in self._config:
                d.update(self._config[section].get('alias', {}))
        # connection aliases
        if connection is not None:
            d.update(self._config[connection].get('alias', {}))
        return d

    def substitute_alias(self, unparsed_args, *, service_name, connection=None):
        alias_name = unparsed_args[0]
        extra_cmds = unparsed_args[1:]
        aliases = self.aliases(service_name=service_name, connection=connection)

        alias_cmd = aliases.get(alias_name)
        if alias_cmd is None:
            return unparsed_args

        alias_cmd = alias_cmd.strip()

        if alias_cmd[0] == '!':
            run_shell_cmd(alias_cmd[1:] + ' ' + ' '.join(shlex.quote(s) for s in extra_cmds))

        params = shell_split(alias_cmd)
        params.extend(extra_cmds)
        return params

    @property
    def connection(self):
        return self._config['connection'] if 'connection' in self._config else None

    def __getitem__(self, key):
        return self._config[key]
