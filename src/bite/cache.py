import configparser
from enum import Enum
from http.cookiejar import LWPCookieJar
import os
import stat

from snakeoil.demandload import demandload

from .exceptions import BiteError

demandload(
    'bite:const',
    'gpg',
    'io:StringIO',
)


def csv2tuple(s):
    return tuple(x.strip() for x in s.split(','))


def iter2csv(x):
    return ', '.join(map(str, x))


def ident(x):
    return x


class Cache(object):

    def __init__(self, *, connection, defaults=None, converters=None):
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
                os.makedirs(os.path.dirname(path), exist_ok=True)
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

    def __init__(self, connection, path=None, token=None, gpgkeys=()):
        self.token = token
        self._gpgkeys = gpgkeys

        if path is not None:
            self.path = path
        elif connection is not None:
            self.path = os.path.join(const.USER_CACHE_PATH, 'auth', f'{connection}.gpg')
        else:
            self.path = None

    def write(self, token):
        if token is None:
            return

        # don't overwrite custom auth files
        if self.path is not None and self.path.endswith('.gpg'):
            try:
                with gpg.Context() as c:
                    cipertext, _result, _sign_result = c.encrypt(
                        token.encode(), recipients=self._gpgkeys, sign=False)
            except gpg.errors.GpgError as e:
                raise BiteError(f'failed encrypting auth token: {e}')

            os.makedirs(os.path.dirname(self.path), mode=0o700, exist_ok=True)
            try:
                with open(self.path, 'wb') as f:
                    f.write(cipertext)
                os.chmod(self.path, stat.S_IREAD | stat.S_IWRITE)
            except (PermissionError, IsADirectoryError) as e:
                raise BiteError(f'failed writing auth token: {self.path!r}: {e.strerror}')

    def read(self):
        if self.path is not None and os.path.exists(self.path):
            if self.path.endswith('.gpg'):
                try:
                    with open(self.path, 'rb') as f:
                        try:
                            with gpg.Context() as c:
                                plaintext, _result, _verify_result = c.decrypt(f)
                        except gpg.errors.GpgError as e:
                            raise BiteError(f'failed decrypting auth token: {self.path!r}: {e}')
                    token = plaintext.decode().strip()
                except IOError as e:
                    raise BiteError(f'failed reading auth token: {self.path!r}: {e}')
            else:
                try:
                    with open(self.path, 'r') as f:
                        token = f.read().strip()
                except IOError as e:
                    raise BiteError(f'failed reading auth token: {self.path!r}: {e}')
            self.token = token

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
        return len(str(self))


class Cookies(LWPCookieJar):
    """Cookiejar wrapper that uses GPGME to encrypt/decrypt cookies."""

    class _Exists(Enum):
        NOTEXISTS = 0
        EXISTS = 1
        CHANGED = 2

    def __init__(self, connection, gpgkeys=()):
        self._exist = self._Exists.NOTEXISTS
        self._gpgkeys = gpgkeys
        super().__init__()
        if connection is not None:
            self._path = os.path.join(const.USER_CACHE_PATH, 'cookies', f'{connection}.gpg')
        else:
            self._path = None

    def __bool__(self):
        return self._exist != self._Exists.NOTEXISTS

    def set_cookie(self, cookie):
        self._exist = self._Exists.CHANGED
        super().set_cookie(cookie)

    def save(self, filename=None, ignore_discard=False, ignore_expires=False):
        cookie_str = self.as_lwp_str(ignore_discard, ignore_expires)
        filename = filename if filename is not None else self._path
        if self._exist is self._Exists.CHANGED and filename is not None:
            # header needed since loading process checks for it
            cookie_bytes = b"#LWP-Cookies-2.0\n" + cookie_str.encode()
            try:
                with gpg.Context() as c:
                    cipertext, _result, _sign_result = c.encrypt(
                        cookie_bytes, recipients=self._gpgkeys, sign=False)
            except gpg.errors.GpgError as e:
                raise BiteError(f'failed encrypting cookies: {e}')

            os.makedirs(os.path.dirname(filename), mode=0o700, exist_ok=True)
            try:
                with open(filename, 'wb') as f:
                    f.write(cipertext)
                os.chmod(self._path, stat.S_IREAD | stat.S_IWRITE)
            except IOError as e:
                raise BiteError(f'failed writing cookies: {filename!r}: {e}')

    def load(self, filename=None, ignore_discard=False, ignore_expires=False):
        filename = filename if filename is not None else self._path
        if filename is not None:
            try:
                with open(filename, 'rb') as f:
                    try:
                        with gpg.Context() as c:
                            plaintext, _result, _verify_result = c.decrypt(f)
                    except gpg.errors.GpgError as e:
                        raise BiteError(f'failed decrypting cookies: {filename!r}: {e}')
                self._really_load(
                    StringIO(plaintext.decode()), filename, ignore_discard, ignore_expires)
                if self.as_lwp_str:
                    self._exist = self._Exists.EXISTS
            except FileNotFoundError:
                # connection doesn't have a saved cache file yet
                pass
            except IOError as e:
                raise BiteError(f'failed loading cookies: {filename!r}: {e}')
