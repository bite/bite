import configparser
import os

from snakeoil.demandload import demandload
from snakeoil.klass import jit_attr
from snakeoil.mappings import ImmutableDict

from .exceptions import BiteError

demandload('bite:const')


class Config(object):

    def __init__(self, path=None, config=None, init=True, args=None):
        self._config = config if config is not None else configparser.ConfigParser()
        self.connection = None

        if init:
            system_config = os.path.join(const.CONFIG_PATH, 'bite.conf')
            user_config = os.path.join(const.USER_CONFIG_PATH, 'bite.conf')

            paths = [(system_config, True), (user_config, False)]
            if path: paths.append((path, True))

            for path, force in paths:
                self.load(paths=path, force=force)

            default_connection = self._config.defaults().get('connection', None)
            if default_connection is not None:
                self._config.remove_option('DEFAULT', 'connection')

            if args is not None:
                # Fallback to using the default connection setting from the config if not
                # specified on the command line and --base/--service options are also
                # unspecified.
                if args.connection is not None:
                    self.connection = args.connection
                elif args.base is None and args.service is None:
                    args.connection = default_connection
                    self.connection = default_connection
                else:
                    self.connection = None

                # Load system connection settings and then user connection settings --
                # later settings override earlier ones. Note that only the service config
                # files matching the name of the selected connection are loaded.
                self.load(connection=self.connection)

                if self.connection and not self._config.has_section(self.connection):
                    raise BiteError(f'unknown connection: {self.connection!r}')

                # pop base and service settings from the config and add them to parsed args
                # if not already specified on the command line
                for attr in ('base', 'service'):
                    if getattr(args, attr, None) is None:
                        setattr(args, attr, self._config.get(self.connection, attr, fallback=None))
                    self._config.remove_option(self.connection, attr)

    @classmethod
    def load_all(cls):
        config = cls(init=False)
        config.load(paths=tuple(cls.service_files()))
        return config

    @jit_attr
    def opts(self):
        if self.connection is not None:
            return ImmutableDict(self._config.items(self.connection))
        return ImmutableDict(self._config.defaults())

    def load(self, *, paths=(), connection=None, force=True):
        if isinstance(paths, str):
            paths = (paths,)
        if connection is not None:
            paths += tuple(self.service_files(connection=connection))

        for path in paths:
            try:
                if force:
                    with open(path) as f:
                        self._config.read_file(f)
                else:
                    self._config.read(path)
            except IOError as e:
                raise BiteError(f'cannot load config file {e.filename!r}: {e.strerror}')

    @staticmethod
    def service_files(connection=None, user_dir=True):
        """Return iterator of service files optionally matching a given connection name."""
        system_services_dir = os.path.join(const.DATA_PATH, 'services')
        user_services_dir = os.path.join(const.USER_DATA_PATH, 'services')

        service_dirs = [system_services_dir]
        if user_dir and os.path.exists(user_services_dir):
            service_dirs.append(user_services_dir)

        for service_dir in service_dirs:
            if connection is not None:
                p = os.path.join(service_dir, connection)
                if os.path.exists(p):
                    yield p
            else:
                for service_file in os.listdir(service_dir):
                    if not service_file.startswith('.'):
                        yield os.path.join(service_dir, service_file)

    # proxied ConfigParser methods

    def has_section(self, name):
        return self._config.has_section(name)

    def sections(self):
        # TODO: filter out a more generic, fake nested template name?
        return [x for x in self._config.sections() if x != ':alias:']

    def items(self, *args, **kw):
        return self._config.items(*args, **kw)

    def get(self, *args, **kw):
        return self._config.get(*args, **kw)
