from functools import wraps
import getpass
from io import BytesIO
from itertools import chain
import os
import subprocess
import sys
import tarfile
import textwrap

from snakeoil.strings import pluralism
from snakeoil.demandload import demandload

from ..exceptions import AuthError, BiteError
from ..objects import TarAttachment
from ..utils import confirm, get_input

demandload('bite:const')


def login_retry(func):
    """Decorator that forces authentication on retry.

    The original function is run and if it fails with an authentication
    failure, login privileges are forcibly enabled and the function is rerun.
    """
    @wraps(func)
    def wrapper(self, *args, **kw):
        try:
            return func(self, *args, **kw)
        except AuthError as e:
            if self.skip_auth or (self.service.authenticated and not e.expired):
                raise e
            # don't show redundant output from retried commands
            self.quiet = True
            if e.expired and self.service.auth:
                self.log('Warning: your auth token has expired', prefix=' ! ')
                self.service.auth.remove()
                self.log('Generating new auth token')
            self.login()
            return func(self, *args, **kw)
    return wrapper


def login_required(func):
    """Decorator that forces authentication to be enabled."""
    @wraps(func)
    def wrapper(self, *args, **kw):
        self.login()
        return func(self, *args, **kw)
    return wrapper


class Cli(object):
    """Generic commandline interface for a service."""

    _service = None

    def __init__(self, service, quiet=False, verbose=False, color=False, connection=None,
                 passwordcmd=None, skip_auth=True, **kw):
        self.service = service
        self.quiet = quiet
        self.verbose = verbose
        self.color = color
        self.passwordcmd = passwordcmd
        self.skip_auth = skip_auth
        self.wrapper = textwrap.TextWrapper(width=const.COLUMNS - 3)

        # Login if all credentials provided on launch and not skipping;
        # otherwise, credentials will be requested when needed.
        if self.skip_auth:
            self.service.auth.token = None
        elif self.service.user is not None and any((self.service.password, self.passwordcmd)):
            self.login()

        self.log(f'Service: {self.service}')

    def login(self):
        """Login to a service and try to cache the authentication token."""
        if self.skip_auth:
            return

        # fallback to manual user/pass login
        if not self.service.auth:
            user = self.service.user
            password = self.service.password
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

            self.service.login(user, password)

    @login_retry
    def get(self, ids, dry_run=False, browser=False, **kw):
        """Get item(s) from a service and all related info."""
        if not ids:
            raise RuntimeError(f'No {self.service.item.type} ID(s) specified')

        if browser:
            if self.service.item_endpoint is None:
                raise BiteError(f"no web endpoint defined for {self.service.item.type}s")

            for id in ids:
                url = self.service.base.rstrip('/') + self.service.item_endpoint + str(id)
                self.log_t(f'Launching {self.service.item.type} in browser: {const.BROWSER} {url}')

                try:
                    subprocess.Popen(
                        [const.BROWSER, url],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                except (PermissionError, FileNotFoundError) as e:
                    raise BiteError(f'failed running browser: {const.BROWSER}: {e.strerror}')
        else:
            request = self.service.GetRequest(ids, **kw)
            self.log_t(f"Getting {self.service.item.type}{pluralism(ids)}: {', '.join(map(str, ids))}")

            if dry_run: return
            data = request.send()
            lines = chain.from_iterable(self._render_item(item, **kw) for item in data)
            print(*lines, sep='\n')

    @login_retry
    @login_required
    def attach(self, ids, dry_run=False, **kw):
        """Attach a file to a specified item given a filename."""
        if dry_run: return
        data = self.service.add_attachment(ids, **kw)
        self.log_t(f"{repr(filename)} attached to {self.service.item.type}{pluralism(ids)}: \
                   {', '.join(map(str, ids))}")

    @login_retry
    def attachments(self, ids, dry_run=False, item_id=False, output_url=False, browser=False, **kw):
        """Get attachments from a service."""
        # skip pulling data if we don't need it
        get_data = (not output_url and not browser)

        if item_id:
            request = self.service.AttachmentsRequest(ids=ids, get_data=get_data)
            item_str = f' from {self.service.item.type}'
            plural = '(s)'
        else:
            request = self.service.AttachmentsRequest(attachment_ids=ids, get_data=get_data)
            item_str = ''
            plural = pluralism(ids)

        self.log_t(f"Getting attachment{plural}{item_str}: {', '.join(map(str, ids))}")

        def _output_urls(ids):
            for id in ids:
                print(self.service.base.rstrip('/') + self.service.attachment_endpoint + str(id))

        def _launch_browser(ids):
            if self.service.attachment_endpoint is None:
                raise BiteError("no web endpoint defined for attachments")

            for id in ids:
                url = self.service.base.rstrip('/') + self.service.attachment_endpoint + str(id)
                self.log_t('Launching attachment in browser: {const.BROWSER} {url}')

                try:
                    subprocess.Popen(
                        [const.BROWSER, url],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                except (PermissionError, FileNotFoundError) as e:
                    raise BiteError(f'failed running browser: {const.BROWSER}: {e.strerror}')

        if not item_id and (output_url or browser):
            if output_url:
                _output_urls(ids)
            elif browser:
                _launch_browser(ids)
        else:
            if dry_run: return
            attachments = request.send()

            # Attachment requests yield lists of attachments -- each list
            # corresponds to the attachments for given item ID or a single list
            # of all attachments requested.
            attachments = chain.from_iterable(attachments)

            if output_url:
                _output_urls(x.id for x in attachments)
            elif browser:
                _launch_browser(x.id for x in attachments)
            else:
                self._process_attachments(attachments, **kw)

    def _process_attachments(self, attachments, show_metadata=False, view_attachment=False,
                             save_to=None, **kw):
        """Process a list of attachment objects."""
        for f in attachments:
            if view_attachment:
                self._view_attachment(f, show_metadata)
            else:
                if save_to is not None:
                    path = os.path.join(save_to, f.filename)
                else:
                    path = os.path.join(os.getcwd(), f.filename)
                self._save_attachment(f, path=path)

    def _view_attachment(self, f, show_metadata):
        """Output attachment data to stdout."""
        compressed = ['x-bzip2', 'x-bzip', 'x-gzip', 'gzip', 'x-tar', 'x-xz']
        mime_type, mime_subtype = f.mimetype.split('/')
        if sys.stdout.isatty() and not (mime_type == 'text' or mime_subtype in compressed):
            self.log(f' ! Warning: The attachment {repr(f.filename)} has type {f.mimetype}')
            if not confirm('Are you sure you want to view it?'):
                return

        self.log(f'Viewing file: {f.filename}')

        if mime_subtype == 'x-tar':
            tar_file = tarfile.open(fileobj=BytesIO(f.read()))
            if show_metadata:
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
                        prefix = f'=== {tarinfo_file.path} '
                        print(prefix + '=' * (const.COLUMNS - len(prefix)))
                        sys.stdout.write(TarAttachment(tarfile=tar_file, cfile=tarinfo_file).data())
        else:
            sys.stdout.write(f.read().decode())

    def _save_attachment(self, f, path):
        """Save attachment to a specified path."""
        if os.path.exists(path):
            print(f' ! Warning: existing file: {repr(path)}')
            if not confirm('Do you want to overwrite it?'):
                return

        self.log(f'Saving attachment: {repr(path)}')
        try:
            f.write(path)
        except IOError as e:
            raise BiteError(f'error creating file: {repr(path)}: {e.strerror}')

    @login_retry
    @login_required
    def modify(self, ids, ask=False, dry_run=False, **kw):
        """Modify an item on the service."""
        request = self.service.ModifyRequest(ids, **kw)

        self.log_t(f"Modifying {self.service.item.type}{pluralism(ids)}: {', '.join(map(str, ids))}")
        self.log(request.options, prefix='')

        if ask:
            if not confirm(prompt=f'Modify {self.service.item.type}{pluralism(ids)}?', default=True):
                self.log('Modification aborted')
                return

        if dry_run: return
        data = request.send()
        lines = chain.from_iterable(self._render_changes(item, **kw) for item in data)
        print(*lines, sep='\n')

    @login_retry
    @login_required
    def create(self, ask=False, batch=False, dry_run=False, **kw):
        """Create an item on the service."""
        options_log = kw.pop('options_log')

        for line in options_log:
            self.log(line, prefix='')

        if ask or not batch:
            if not confirm(prompt=f'Submit {self.service.item.type}?', default=True):
                self.log('Submission aborted')
                return

        if dry_run: return

        try:
            data = self.service.create(**kw)
        except ValueError as e:
            raise BiteError(e)

        if sys.stdout.isatty():
            self.log(f'Submitted {self.service.item.type} {data}')
        else:
            sys.stdout.write(str(data))

    def search(self, dry_run=False, **kw):
        """Search for items on the service."""
        request = self.service.SearchRequest(**kw)

        self.log(f'Searching for {self.service.item.type}s with the following options:')
        self.log(request.options, prefix='   - ')

        if dry_run: return
        data = request.send()

        lines = self._render_search(data, **kw)
        count = 0
        for line in lines:
            count += 1
            print(line[:const.COLUMNS])
        self.log(f"{count} {self.service.item.type}{pluralism(count)} found.")

    def _header(self, char, msg):
        return f'{char * 3} {msg} {char * (const.COLUMNS - len(msg) - 5)}'

    def log(self, msg, newline=True, truncate=False, prefix=' * '):
        if isinstance(msg, list):
            for i, line in enumerate(msg):
                if i > 0:
                    msg[i] = prefix + msg[i]
            msg = '\n'.join(msg)

        if sys.stdout.isatty():
            output = sys.stdout
        else:
            output = sys.stderr

        msg = prefix + msg
        if truncate:
            msg = self._truncate(msg)
        if not self.quiet:
            if newline:
                print(msg, file=output)
            else:
                print(msg, end='', file=output)

    def log_t(self, *args, **kw):
        """Wrapper for truncated output."""
        self.log(*args, truncate=True, **kw)

    def _truncate(self, stuff):
        if len(stuff) <= const.COLUMNS:
            return stuff
        else:
            line = [self.wrapper.wrap(stuff)[0]]
            line.append('...')
            return ' '.join(line)

    def _iter_lines(self, data, wrap=True):
        if isinstance(data, str):
            sep = ''
        else:
            sep = '\n\n'

        for line in sep.join(data).splitlines():
            no_mod = (line == '-' * const.COLUMNS or len(line) <= const.COLUMNS or
                      not sys.stdout.isatty())
            if no_mod:
                yield line
            elif wrap:
                yield self.wrapper.fill(line)
            else:
                yield line[:const.COLUMNS]

    def cache(self, update=False, remove=False, *args, **kw):
        if update:
            updates = self.service.cache_updates
            if updates != self.service.cache:
                self.service.cache.write(updates=updates)
        elif remove:
            self.service.cache.remove()

    def _render_changes(self, data, **kw):
        raise NotImplementedError

    def _render_search(self, data, fields=None, output=None, **kw):
        """Render search data for output."""
        if output is None:
            if fields is None:
                fields = ('id', 'owner', 'title')
                output = '{} {:<20} {}'
            else:
                output = ' '.join('{}' for x in fields)

        for item in data:
            if output == '-':
                for field in fields:
                    try:
                        value = getattr(item, field)
                    except AttributeError:
                        raise BiteError(f'invalid field: {repr(field)}')
                    if value is None:
                        continue
                    if isinstance(value, list):
                        yield from map(str, value)
                    else:
                        yield value
            else:
                values = (getattr(item, field) for field in fields)
                yield output.format(*values)

    def _render_item(self, item, **kw):
        """Render item data for output."""
        yield '=' * const.COLUMNS
        for line in str(item).splitlines():
            if len(line) <= const.COLUMNS:
                yield line
            else:
                yield self.wrapper.fill(line)

        if item.attachments:
            attachments = [str(a) for a in item.attachments]
            if attachments:
                if str(item):
                    yield ''
                yield from attachments

        if item.events and (str(item) or item.attachments):
            yield ''
        yield from self._iter_lines(str(x) for x in item.events)
