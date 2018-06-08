import configparser
import os

from snakeoil import klass
from snakeoil.demandload import demandload
from snakeoil.mappings import ImmutableDict

from .exceptions import BiteError

demandload('bite:const')


class Config(object):

    def __init__(self, path=None, config=None,
                 connection=klass._sentinel, base=klass._sentinel, service=klass._sentinel):
        self._config = config if config is not None else configparser.ConfigParser()
        self.connection = None if connection is klass._sentinel else connection

        if connection is not klass._sentinel:
            # load system/user configs
            if base is not klass._sentinel and service is not klass._sentinel:
                system_config = os.path.join(const.CONFIG_PATH, 'bite.conf')
                user_config = os.path.join(const.USER_CONFIG_PATH, 'bite.conf')

                paths = [(system_config, True), (user_config, False)]
                if path: paths.append((path, True))

                for path, force in paths:
                    self.load(paths=path, force=force)

                default_connection = self._config.defaults().get('connection', None)
                if default_connection is not None:
                    self._config.remove_option('DEFAULT', 'connection')

            # Fallback to using the default connection setting from the config if not
            # specified on the command line and --base/--service options are also
            # unspecified.
            if connection is not None:
                self.connection = connection
            elif base is None and service is None:
                connection = default_connection
                self.connection = default_connection
            else:
                self.connection = None

            # Load system connection settings and then user connection settings --
            # later settings override earlier ones. Note that only the service config
            # files matching the name of the selected connection are loaded.
            self.load(connection=self.connection)

            if self.connection and not self._config.has_section(self.connection):
                raise BiteError(f'unknown connection: {self.connection!r}')

    @klass.jit_attr
    def opts(self):
        if self.connection is not None:
            return ImmutableDict(self._config.items(self.connection))
        return ImmutableDict(self._config.defaults())

    def load(self, *, paths=(), connection=klass._sentinel, force=True):
        if isinstance(paths, str):
            paths = (paths,)
        if connection is not klass._sentinel:
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
                conf = os.path.join(service_dir, connection)
                if os.path.exists(conf):
                    yield conf
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

    def remove_option(self, *args, **kw):
        return self._config.remove_option(*args, **kw)
