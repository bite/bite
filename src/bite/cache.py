import configparser
from http.cookiejar import LWPCookieJar
import os
import stat

from snakeoil.demandload import demandload

from .exceptions import BiteError

demandload('bite:const')


def csv2tuple(s):
    return tuple(x.strip() for x in s.split(','))


def iter2csv(x):
    return ', '.join(map(str, x))


def ident(x):
    return x


class Cache(object):

    def __init__(self, connection, defaults=None, converters=None):
        self._settings = {}
        if defaults is not None:
            self._settings.update(defaults)

        if converters is None:
            converters = {}
        self.converters = {}
        self.converters['read'] = converters
        self.converters['write'] = {
            'tuple': iter2csv,
            'str': ident,
        }

        self.connection = connection
        if self.connection is not None:
            self.path = os.path.join(const.USER_CACHE_PATH, 'config', self.connection)
            self.read()
        else:
            self.path = None

    def read(self, path=None):
        """Load cached data from a config file."""
        path = path if path is not None else self.path

        if path is not None:
            config = configparser.ConfigParser()
            try:
                with open(path, 'r') as f:
                    config.read_file(f)
                settings = config.items(self.connection)
            except IOError:
                settings = ()
            self._settings.update(
                (k, self.converters['read'].get(k, ident)(v))
                for k, v in settings)

    def write(self, path=None, updates=None):
        """Write cache updates to a config file."""
        path = path if path is not None else self.path

        if path is not None:
            d = updates if updates is not None else self._settings
            d = {k: self.converters['write'].get(type(v).__name__, ident)(v)
                for k, v in d.items()}

            if self._settings:
                try:
                    os.makedirs(os.path.dirname(path))
                except FileExistsError:
                    pass
                config = configparser.ConfigParser()
                config[self.connection] = d
                with open(path, 'w') as f:
                    config.write(f)

    def remove(self, path=None):
        """Remove cache file if it exists."""
        path = path if path is not None else self.path

        if path is not None:
            try:
                os.remove(path)
            except FileNotFoundError:
                pass
            except IOError as e:
                raise BiteError(f'unable to remove cache: {path!r}: {e.strerror}')

    ## support dictionary access methods

    def update(self, *args, **kwargs):
        self._settings.update(*args, **kwargs)

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

    def __eq__(self, x):
        return x == self._settings

    def clear(self):
        return self._settings.clear()

    def copy(self):
        return self._settings.copy()

    def has_key(self, k):
        return k in self._settings

    def get(self, key):
        return self._settings.get(key)

    def keys(self):
        return self._settings.keys()

    def values(self):
        return self._settings.values()

    def items(self):
        return self._settings.items()


class Auth(object):

    def __init__(self, connection, path=None, token=None):
        self.token = token

        if path is not None:
            self.path = path
        elif connection is not None:
            self.path = os.path.join(const.USER_CACHE_PATH, 'auth', connection)
        else:
            self.path = None

        if self.token is None:
            self.read()

    def write(self, token):
        if token is None:
            return

        if self.path is not None:
            try:
                os.makedirs(os.path.dirname(self.path))
            except FileExistsError:
                pass

            try:
                with open(self.path, 'w+') as f:
                    os.chmod(self.path, stat.S_IREAD | stat.S_IWRITE)
                    f.write(token)
            except (PermissionError, IsADirectoryError) as e:
                raise BiteError(f'failed writing auth token to {self.path!r}: {e.strerror}')

    def read(self):
        if self.path is not None:
            try:
                with open(self.path, 'r') as f:
                    self.token = f.read().strip()
            except IOError:
                self.token = None

    def update(self, token):
        self.token = token
        self.write(token)

    def remove(self):
        """Remove an authentication token."""
        if self.path is not None:
            try:
                os.remove(self.path)
            except FileNotFoundError:
                pass
            except IOError as e:
                raise BiteError(f'unable to remove cache: {self.path!r}: {e.strerror}')
        self.reset()

    def reset(self):
        """Reset an authentication token."""
        self.token = None

    def __str__(self):
        if self.token is None:
            return ''
        return self.token

    def __bool__(self):
        return bool(self.token)

    def __len__(self):
        return len(self.token)


class Cookies(LWPCookieJar):

    def __init__(self, connection):
        super().__init__()
        if connection is not None:
            self._path = os.path.join(const.USER_CACHE_PATH, 'cookies', connection)
        else:
            self._path = None

    def save(self, filename=None, *args, **kw):
        if filename is None:
            filename = self._path
        if self._path is not None:
            try:
                os.makedirs(os.path.dirname(self._path))
            except FileExistsError:
                pass
        try:
            super().save(filename=filename, *args, **kw)
            os.chmod(self._path, stat.S_IREAD | stat.S_IWRITE)
        except ValueError:
            # running without a configured connection
            if filename is None:
                pass
            else:
                raise

    def load(self, filename=None, *args, **kw):
        if filename is None:
            filename = self._path
        try:
            super().load(filename=filename, *args, **kw)
        except FileNotFoundError:
            # connection doesn't have a saved cache file yet
            pass
        except ValueError:
            # running without a configured connection
            if filename is None:
                pass
            else:
                raise
