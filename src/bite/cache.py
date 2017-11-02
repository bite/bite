import os
import configparser

from . import const
from .exceptions import BiteError

class Cache(object):

    def __init__(self, connection, defaults=None):
        self.connection = connection
        self.path = os.path.join(const.USER_CACHE_PATH, 'config', connection)

        self._settings = {}
        if defaults is not None:
            self._settings.update(defaults)

        self.read()

    def read(self, path=None):
        """Load cached data from a config file."""
        if path is None:
            path = self.path

        config = configparser.ConfigParser()
        try:
            with open(path, 'r') as f:
                config.read_file(f)
            settings = config.items(self.connection)
        except IOError:
            settings = ()
        # XXX: currently assumes all cached data is CSV
        self._settings.update(
            (k, tuple(x.strip() for x in v.split(',')))
            for k, v in settings)

    def write(self, path=None):
        """Write cache updates to a config file."""
        if path is None:
            path = self.path

        if self._settings:
            try:
                os.makedirs(os.path.dirname(self.path))
            except FileExistsError:
                pass
            config = configparser.ConfigParser()
            config[self.connection] = self._settings
            with open(self.path, 'w') as f:
                config.write(f)

    def update(self, *args, **kwargs):
        """Update cached data for the service."""
        self._settings.update(*args, **kwargs)

    def remove(self):
        """Remove cache file if it exists."""
        try:
            os.remove(self.path)
        except FileNotFoundError:
            pass
        except IOError as e:
            raise BiteError('unable to remove cache: {!r}: {}'.format(self.path, e.strerror))

    def __setitem__(self, key, item):
        self._settings[key] = item

    def __getitem__(self, key):
        return self._settings[key]

    def __repr__(self):
        return repr(self._settings)

    def __len__(self):
        return len(self._settings)

    def __delitem__(self, key):
        del self._settings[key]

    def clear(self):
        return self._settings.clear()

    def copy(self):
        return self._settings.copy()

    def has_key(self, k):
        return k in self._settings

    def keys(self):
        return self._settings.keys()

    def values(self):
        return self._settings.values()

    def items(self):
        return self._settings.items()
