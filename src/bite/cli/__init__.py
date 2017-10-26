import codecs
import getpass
from io import StringIO
import locale
import os
from shutil import get_terminal_size
import stat
import subprocess
import sys
import tarfile
import textwrap
from urllib.parse import urlparse

from ..const import USER_CACHE_PATH
from ..exceptions import AuthError, CliError
from ..objects import TarAttachment
from ..utils import confirm, get_input

def loginretry(func):
    """Forces authentication on second request if the initial request was unauthenticated and failed due to insufficient permissions."""
    def wrapper(self, *args, **kw):
        try:
            return func(self, *args, **kw)
        except AuthError as e:
            if self.skip_auth:
                raise e
            # don't show redundant output from retried commands
            self.quiet = True
            if e.expired and self.service.auth_token is not None:
                self.log('Warning: your auth token has expired', prefix=' ! ')
                self.remove_auth_token()
                self.log('Generating new auth token')
            self.login()
            self.load_auth_token()
            return func(self, *args, **kw)
    return wrapper

def loginrequired(func):
    """Authentication is required to use this functionality."""
    def wrapper(self, *args, **kw):
        self.login()
        return func(self, *args, **kw)
    return wrapper


class Cli(object):
    """Generic commandline interface for a service."""

    def __init__(self, service, connection=None, quiet=False, columns=None,
                 encoding=None, passwordcmd=None, auth_file=None, skip_auth=True, **kw):
        self.service = service
        self.connection = connection
        self.quiet = quiet
        self.passwordcmd = passwordcmd
        self.columns = columns or get_terminal_size()[0]
        self.wrapper = textwrap.TextWrapper(width = self.columns)
        self.skip_auth = skip_auth
        self.auth_file = auth_file

        if encoding:
            self.enc = encoding
        else:
            try:
                self.enc = locale.getpreferredencoding()
            except:
                self.enc = 'utf-8'

        # set preferred stdin/stdout encodings when redirecting
        if sys.stdout.encoding is None:
            sys.stdout = codecs.getwriter(self.enc)(sys.stdout)
        if sys.stdin.encoding is None:
            sys.stdin = codecs.getreader(self.enc)(sys.stdin)

        if self.auth_file is None:
            url = urlparse(self.service.base)
            if len(url.path) <= 1:
                auth_file = url.netloc
            else:
                auth_file = '{}{}'.format(url.netloc, url.path.replace('/', '-'))
            self.auth_file = os.path.join(USER_CACHE_PATH, 'auth', auth_file)

        auth_requested = any(
            ((auth_file or os.path.exists(self.auth_file)), self.service.auth_token, self.passwordcmd,
             self.service.user, self.service.password))

        # login if requested; otherwise, login will be required when necessary
        if auth_requested:
            self.login()

        if sys.stdin.isatty():
            self.log('Service: {}'.format(self.service))

    def login(self):
        """Login to a service and try to cache the authentication token."""
        if self.skip_auth:
            return

        self.load_auth_token()

        # fallback to manual user/pass login
        if self.service.auth_token is None:
            user, password = self.get_login_data(self.service.user, self.service.password)
            self.service.login(user, password)
            self.cache_auth_token()

    def get_login_data(self, user=None, password=None):
        """Request user and password info from the user."""
        if user is None:
            self.log('No username given.')
            user = get_input('Username: ')

        if password is None:
            if not self.passwordcmd:
                self.log('No password given.')
                password = getpass.getpass()
            else:
                process = subprocess.Popen(
                    self.passwordcmd.split(), shell=False, stdout=subprocess.PIPE)
                password, _ = process.communicate()
        return user, password

    @loginretry
    def get(self, dry_run, ids, filters, browser=False, **kw):
        if not ids:
            raise RuntimeError('No {} ID(s) specified'.format(self.service.item))

        if browser:
            if self.service.item_web_endpoint is None:
                raise CliError("service doesn't define a web endpoint")

            for id in ids:
                url = self.service.base.rstrip('/') + self.service.item_web_endpoint + str(id)
                browser = os.environ.get('BROWSER', 'xdg-open')
                self.log(self._truncate('Launching {} in browser: {} {!r}'.format(
                    self.service.item, browser, url)))

                try:
                    subprocess.run([browser, "{}".format(url)],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                except (PermissionError, FileNotFoundError) as e:
                    raise CliError('failed running browser {!r}: {}'.format(browser, e.strerror))
        else:
            self.log(self._truncate('Getting {}(s): {}'.format(self.service.item, ', '.join(map(str, ids)))))

            if dry_run: return
            data = self.service.get(ids, **kw)
            if filters is not None:
                for fcn in filters:
                    data = fcn(data)
            self._print_item(data, **kw)

    @loginretry
    @loginrequired
    def attach(self, dry_run, ids, **kw):
        """Attach a file to a specified item given a filename."""
        params = self._attach_params(**kw)
        if dry_run: return
        data = self.service.add_attachment(ids, **params)
        self.log(self._truncate('"{}" attached to {}(s): {}'.format(filename, self.service.item, ', '.join(map(str, ids)))))

    @loginretry
    def attachment(self, dry_run, ids, view, metadata, url, **kw):
        if dry_run: return
        self.attachment_download(ids, view, metadata, url, **kw)

    def attachment_download(self, ids, view, metadata, url, **kw):
        attachments = self.service.get_attachment(ids)

        try:
            for f in attachments:
                if url:
                    print(f.url)
                elif view:
                    self.view_file(f, metadata)
                else:
                    self.save_file(f)
        except ValueError as e:
            raise RuntimeError(e)

    def view_file(self, f, metadata):
        compressed = ['x-bzip2', 'x-bzip', 'x-gzip', 'gzip', 'x-tar', 'x-xz']
        mime_type, mime_subtype = f.mimetype.split('/')
        if sys.stdout.isatty() and not (mime_type == 'text' or mime_subtype in compressed):
            self.log(' ! Warning: The attachment "{}" has type {!r}'.format(f.filename, f.mimetype))
            if not confirm('Are you sure you want to view it?'):
                return

        self.log('Viewing file: {}'.format(f.filename))

        if mime_subtype == 'x-tar':
            tar_file = tarfile.open(fileobj=StringIO.StringIO(f.read()))
            if metadata:
                # show listing of tarfile elements
                tar_file.list()
            else:
                for tarinfo_file in tar_file.getmembers():
                    try:
                        temp = tar_file.extractfile(tarinfo_file)
                    except KeyError:
                        # symlink points to a nonexistent file
                        return

                    if temp is not None:
                        prefix = '=== {} '.format(temp.name)
                        print(prefix + '=' * (self.columns - len(prefix)))
                        sys.stdout.write(TarAttachment(tarfile=tar_file, cfile=tarinfo_file).data())
        else:
            sys.stdout.write(f.read())

    def save_file(self, f):
        if os.path.exists(f.filename):
            print(' ! Warning: The file {!r} already exists'.format(f.filename))
            if not confirm('Do you want to overwrite it?'):
                return

        self.log('Saving file: {}'.format(f.filename))
        try:
            with open(f.filename, 'w+') as save_file:
                os.chmod(f.filename, stat.S_IREAD | stat.S_IWRITE)
                save_file.write(f.read(raw=True))
        except IOError as e:
            raise RuntimeError('Cannot create file {!r}: {}'.format(f.filename, e.strerror))

    @loginretry
    @loginrequired
    def modify(self, ask, dry_run, ids, **kw):
        kw = self._modify_params(**kw)
        request = self.service.modify(ids, **kw)

        self.log(self._truncate('Modifying {}(s): {}'.format(self.service.item,
                               ', '.join(map(str, ids)))))
        self.log(request.options, prefix='')

        if ask:
            if not confirm(prompt='Modify {}(s)?'.format(self.service.item), default=True):
                self.log('Modification aborted')
                return

        if dry_run: return
        data = request.send()
        self.print_changes(data, params=kw)

    @loginretry
    @loginrequired
    def create(self, ask, batch, dry_run, **kw):
        options_log, params = self._create_params(batch, **kw)

        for line in options_log:
            self.log(line, prefix='')

        if ask or not batch:
            if not confirm(prompt='Submit {}?'.format(self.service.item), default=True):
                self.log('Submission aborted')
                return

        if dry_run: return

        try:
            data = self.service.create(**params)
        except ValueError as e:
            raise RuntimeError(e)

        if sys.stdout.isatty():
            self.log('Submitted {} {}'.format(self.service.item, data))
        else:
            sys.stdout.write(str(data))

    def search(self, dry_run, filters, **kw):
        kw = self._search_params(**kw)
        request = self.service.search(**kw)

        if kw['fields'] is None:
            kw['fields'] = request.fields

        self.log('Searching for {}s with the following options:'.format(self.service.item))
        self.log(request.options, prefix='   - ')

        if dry_run: return
        data = request.send()
        if filters is not None:
            for fcn in filters:
                data = fcn(data)
        count = self.print_search(data, **kw)
        if sys.stdout.isatty():
            self.log('{} {}{} found.'.format(count, self.service.item, 's'[count == 1:]))

    def _header(self, char, msg):
        return '{} {} {}'.format(char * 3, msg, char * (self.columns - len(msg) - 5))

    def log(self, msg, newline=True, prefix=' * '):
        if isinstance(msg, list):
            for i, line in enumerate(msg):
                if i > 0:
                    msg[i] = prefix + msg[i]
                if line.endswith('-' * 10):
                    msg[i] = line + '-' * (self.columns - len(line))
            msg = '\n'.join(msg)

        if sys.stdout.isatty():
            output=sys.stdout
        else:
            output=sys.stderr

        msg = prefix + msg
        if not self.quiet:
            if newline:
                print(msg, file=output)
            else:
                print(msg, end='', file=output)

    def _truncate(self, stuff):
        if len(stuff) <= self.columns:
            return stuff
        else:
            line = self.wrapper.wrap(stuff)[0].split()
            line = line[:len(line)-2]
            line.append('...')
            return ' '.join(line)

    def _print_lines(self, stuff, wrap=True):
        if isinstance(stuff, str):
            sep = ''
        else:
            sep = '\n\n'

        for line in sep.join(stuff).splitlines():
            if line == '-' * 10:
                print('-' * self.columns)
            elif len(line) <= self.columns or not sys.stdout.isatty():
                print(line)
            elif wrap:
                print(self.wrapper.fill(line))
            else:
                print(line[:self.columns])

    def cache_auth_token(self):
        # TODO: Move caching to library side to make sure it's only done
        # after successful login or API call of some type and to use with other clients.
        try:
            os.makedirs(os.path.dirname(self.auth_file))
        except FileExistsError:
            pass

        try:
            with open(self.auth_file, 'w+') as f:
                os.chmod(self.auth_file, stat.S_IREAD | stat.S_IWRITE)
                f.write(self.service.auth_token)
        except (PermissionError, IsADirectoryError) as e:
            raise CliError('failed caching auth token to {!r}: {}'.format(
                self.auth_file, e.strerror))

    def load_auth_token(self):
        try:
            with open(self.auth_file, 'r') as f:
                self.service.auth_token = f.read()
        except IOError:
            return None

    def remove_auth_token(self):
        """Remove an authentication token."""
        if confirm(prompt='Remove auth token?', default=True):
            os.remove(self.auth_file)
        else:
            # currently only keep one backup and which is overwritten if it already exists
            self.log('Moving old auth token to {!r}'.format(self.auth_file + '.old'))
            os.rename(self.auth_file, self.auth_file + '.old')
        self.service.auth_token = None

    def _attach_params(self):
        raise NotImplementedError

    def _modify_params(self, *args, **kw):
        return kw

    def _create_params(self):
        raise NotImplementedError

    def _search_params(self, *args, **kw):
        return kw

    def print_changes(self, data, params):
        raise NotImplementedError

    def print_search(self, data, **kw):
        raise NotImplementedError

    @staticmethod
    def _print_item(data, **kw):
        raise NotImplementedError
