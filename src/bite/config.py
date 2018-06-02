import os
import sys

from snakeoil.demandload import demandload

from . import service_classes
from ._vendor import configobj
from .exceptions import BiteError, ConfigError
from .utils import shell_split

demandload(
    'shlex',
    'subprocess',
    'bite:const',
)


class Config(object):

    def __init__(self, path=None, load=True):
        self._config = configobj.ConfigObj(
            list_values=False, file_error=True,
            interpolation='configparser-extended')

        self._system_config = os.path.join(const.CONFIG_PATH, 'bite.conf')
        self._user_config = os.path.join(const.USER_CONFIG_PATH, 'bite.conf')

        if load:
            # load system config
            self.load(self._system_config)

            # optionally load user config, forcibly load if overridden
            if path is None:
                if os.path.exists(self._user_config):
                    path = self._user_config
                else:
                    self._user_config = None
            if path is not None:
                self.load(path)

    def load(self, paths):
        """Load config files."""
        # TODO: add better merging/loading support in configobj directly
        if isinstance(paths, str):
            paths = [paths]

        for path in paths:
            try:
                with open(path) as f:
                    c = configobj.ConfigObj(
                        f.readlines(),
                        file_error=True, list_values=False,
                        interpolation='configparser-extended')
            except (IOError, configobj.ConfigObjError) as e:
                raise ConfigError(path=path, msg=str(e))

            self._config.merge(c)

    def load_all(self):
        """Load all known configuration files."""
        self.load_service(connection=None)

    @staticmethod
    def service_files(connection=None, user_dir=True):
        """Return iterator of service files optionally matching a given connection name."""
        system_dir = os.path.join(const.DATA_PATH, 'services')
        user_dir = os.path.join(const.USER_DATA_PATH, 'services')

        service_dirs = [system_dir]
        if user_dir and os.path.exists(user_dir):
            service_dirs.append(user_dir)

        for service_dir in service_dirs:
            if connection is not None:
                p = os.path.join(service_dir, connection)
                if os.path.exists(p):
                    yield p
            else:
                for service_file in os.listdir(service_dir):
                    if not service_file.startswith('.'):
                        yield os.path.join(service_dir, service_file)

    def load_service(self, connection, user_dir=True):
        """Load service specific configuration files.

        Load system connection settings and then user connection settings --
        later settings override earlier ones. Note that only the service config
        files matching the name of the selected connection are loaded.
        """
        files = tuple(self.service_files(connection, user_dir=user_dir))
        if not files:
            raise BiteError(f'unknown connection: {connection!r}')
        self.load(files)

        # reload user config to override service settings
        if connection and self._user_config is not None:
            self.load(self._user_config)

    def aliases(self, *, service_name, config_opts=None, connection=None):
        """Dictionary of aliases overridden via preference."""
        try:
            # global aliases
            d = self._config.get('alias')
            # inject config settings for interpolation
            d.main._config_opts = config_opts
            # service aliases
            for section in (x.upper() for x in reversed(tuple(service_classes(service_name)))):
                if section in self._config:
                    d.update(self._config[section].get('alias', {}))
            # connection aliases
            if connection is not None:
                d.update(self._config[connection].get('alias', {}))
        except configobj.MissingInterpolationOption as e:
            raise ConfigError(str(e))
        return d

    def substitute_alias(self, unparsed_args, *, service_name,
                         config_opts=None, connection=None, aliases=None):
        alias_name = unparsed_args[0]
        extra_cmds = unparsed_args[1:]
        aliases = aliases if aliases is not None else self.aliases(
            service_name=service_name, config_opts=config_opts, connection=connection)

        try:
            alias_cmd = aliases.get(alias_name)
        except configobj.MissingInterpolationOption as e:
            msg = f'alias {alias_name!r}: {str(e)}'
            raise ConfigError(msg=msg)
        if alias_cmd is None:
            return unparsed_args

        alias_cmd = alias_cmd.strip()

        # Run '!' prefixed aliases in the system shell, security issues with
        # shell injections are the user's responsibility with their config.
        if alias_cmd[0] == '!':
            # TODO: handle failures, errors, and keyboard interrupts better
            p = subprocess.run(
                alias_cmd[1:] + ' ' + ' '.join(shlex.quote(s) for s in extra_cmds),
                stderr=subprocess.PIPE, shell=True)
            try:
                p.check_returncode()
            except subprocess.CalledProcessError as e:
                msg = f'failed running alias {alias_name!r}:\n{p.stderr.decode().strip()}'
                raise BiteError(msg=msg)
            sys.exit(p.returncode)

        params = shell_split(alias_cmd)
        params.extend(extra_cmds)
        if params[0] != alias_name:
            # recursively check aliases if the initial command is different
            return self.substitute_alias(
                params, service_name=service_name,
                config_opts=config_opts, connection=connection, aliases=aliases)
        else:
            return params

    @property
    def connection(self):
        return self._config['connection'] if 'connection' in self._config else None

    def items(self):
        return self._config.items()

    def keys(self):
        return self._config.keys()

    def values(self):
        return self._config.values()

    def get(self, key, default=None):
        try:
            return self._config.get(key, default)
        except configobj.MissingInterpolationOption as e:
            raise BiteError(str(e))

    def __getitem__(self, key):
        return self._config[key]
