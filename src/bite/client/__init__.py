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
from ..utils import confirm, get_input, launch_browser

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
        while True:
            try:
                self.login()
                return func(self, *args, **kw)
            except AuthError as e:
                self.log(str(e))
    return wrapper


def dry_run(func):
    """Decorator that forces a dry run of a method."""
    @wraps(func)
    def wrapper(self, *args, dry_run=False, **kw):
        # skip authentication and monkey patch sending to return an empty dataset
        if dry_run:
            self.skip_auth = True
            self.service.send = lambda *args, **kw: ()
        return func(self, *args, **kw)
    return wrapper


class Client(object):
    """Generic client for a service."""

    _service = None

    def __init__(self, service):
        self.service = service

        # Register client callbacks for service obj. We want this to explode if
        # a Client child doesn't implement all the callbacks requested by the
        # Service class.
        callbacks = (f for f in dir(self.service.client) if not f.startswith('__'))
        for func_name in callbacks:
            func = getattr(self, func_name)
            setattr(self.service.client, func_name, func)


class Cli(Client):
    """Generic commandline interface for a service."""

    def __init__(self, service, quiet=False, verbose=False, debug=False, color=False,
                 connection=None, passwordcmd=None, skip_auth=True, **kw):
        super().__init__(service)
        self.color = color
        self.passwordcmd = passwordcmd
        self.skip_auth = skip_auth
        self.wrapper = textwrap.TextWrapper(width=const.COLUMNS - 3)

        self.quiet = quiet
        self.verbose = verbose
        self.debug = debug

        # Login if all credentials provided on launch and not skipping;
        # otherwise, credentials will be requested when needed.
        if self.skip_auth:
            self.service.auth.reset()
        elif self.service.user is not None and any((self.service.password, self.passwordcmd)):
            self.login()

        self.log(f'Service: {self.service}')

    def get_user_pass(self, msg=None):
        """Request user/password info from the user."""
        user = self.service.user
        password = self.service.password

        if msg is not None:
            self.log(msg)

        if user is None:
            user = get_input('Username: ')
        else:
            print(f'Username: {user}')

        if password is None:
            if not self.passwordcmd:
                password = getpass.getpass()
            else:
                process = subprocess.Popen(
                    self.passwordcmd.split(), shell=False, stdout=subprocess.PIPE)
                password, _ = process.communicate()
        return user, password

    def confirm(self, *args, **kw):
        return confirm(*args, **kw)

    def progress_output(self, s):
        self.log(s)

    def login(self, force=False):
        """Login to a service and try to cache the authentication token."""
        if self.skip_auth and not force:
            return

        # fallback to manual user/pass login
        if not self.service.auth:
            user, password = self.service.user, self.service.password
            while not all((user, password)):
                user, password = self.get_user_pass()
            self.service.login(user=user, password=password)

    @dry_run
    @login_retry
    def get(self, ids, browser=False, output_url=False, **kw):
        """Get item(s) from a service and all related info."""
        if not ids:
            raise RuntimeError(f'No {self.service.item.type} ID(s) specified')

        if browser:
            urls = list(self.service.item_urls(ids))
            self.log_t(f'Launching {self.service.item.type}{pluralism(ids)} in browser: {const.BROWSER}')
            self.log(urls, prefix='   - ')
            launch_browser(urls)
        elif output_url:
            print(*self.service.item_urls(ids), sep='\n')
        else:
            request = self.service.GetRequest(ids=ids, **kw)
            self.log_t(f"Getting {self.service.item.type}{pluralism(ids)}: {', '.join(map(str, ids))}")

            data = request.send()
            lines = chain.from_iterable(self._render_item(item, **kw) for item in data)
            print(*lines, sep='\n')

    @dry_run
    @login_retry
    @login_required
    def attach(self, ids, **kw):
        """Attach a file to a specified item given a filename."""
        request = self.service.AttachRequest(ids=ids, **kw)
        data = request.send()
        self.log_t(f"{filename!r} attached to {self.service.item.type}{pluralism(ids)}: \
                   {', '.join(map(str, ids))}")

    @dry_run
    @login_retry
    def attachments(self, ids, id_map=False, item_id=False, output_url=False,
                    browser=False, **kw):
        """Get attachments from a service."""
        # skip pulling data if we don't need it
        get_data = (not output_url and not browser)

        # extract attachment IDs to display if the service uses ID maps
        display_ids = []
        if id_map:
            for id, a_ids in ids:
                if not a_ids:
                    display_ids.append(f'from {self.service.item.type} {id}')
                else:
                    display_ids.extend(f'{id}:{a}' for a in a_ids)
        else:
            display_ids = ids

        if item_id:
            request = self.service.AttachmentsRequest(ids=ids, get_data=get_data)
            item_str = f' from {self.service.item.type}'
            plural = '(s)'
        else:
            request = self.service.AttachmentsRequest(attachment_ids=ids, get_data=get_data)
            item_str = ''
            plural = pluralism(display_ids)

        self.log_t(f"Getting attachment{plural}{item_str}: {', '.join(map(str, display_ids))}")

        def _launch_browser(ids):
            urls = list(self.service.attachment_urls(ids))
            self.log_t(f'Launching attachment{pluralism(ids)} in browser: {const.BROWSER}')
            self.log(urls, prefix='   - ')
            launch_browser(urls)

        if not item_id and (output_url or browser):
            if output_url:
                print(*self.service.attachment_urls(ids), sep='\n')
            elif browser:
                _launch_browser(ids)
        else:
            attachments = request.send()

            # Attachment requests yield lists of attachments -- each list
            # corresponds to the attachments for given item ID or a single list
            # of all attachments requested.
            attachments = chain.from_iterable(attachments)

            if output_url:
                ids = (x.id for x in attachments)
                print(*self._attachment_urls(ids), sep='\n')
            elif browser:
                _launch_browser(x.id for x in attachments)
            else:
                save_to = kw.get('save_to')
                if save_to is not None:
                    os.makedirs(save_to, exist_ok=True)
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
        compressed = set(['x-bzip2', 'x-bzip', 'x-gzip', 'gzip', 'x-tar', 'x-xz'])
        mime_type, mime_subtype = f.mimetype.split('/')
        if sys.stdout.isatty() and not (mime_type == 'text' or mime_subtype in compressed):
            self.log(f' ! Warning: The attachment {f.filename!r} has type {f.mimetype}')
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
            data = f.read().decode()
            sys.stdout.write(data)
            if not data.endswith('\n'):
                self.log('', prefix='')

    def _save_attachment(self, f, path):
        """Save attachment to a specified path."""
        if os.path.exists(path):
            print(f' ! Warning: existing file: {path!r}')
            if not confirm('Do you want to overwrite it?'):
                return

        self.log(f'Saving attachment: {path!r}')
        f.write(path)

    @dry_run
    @login_retry
    @login_required
    def modify(self, ask=False, **kw):
        """Modify an item on the service."""
        request = self.service.ModifyRequest(params=kw)
        ids = request.params['ids']

        self.log_t(f"Modifying {self.service.item.type}{pluralism(ids)}: {', '.join(map(str, ids))}")
        self.log(request.options, prefix='')

        if ask:
            if not confirm(prompt=f'Modify {self.service.item.type}{pluralism(ids)}?', default=True):
                self.log('Modification aborted')
                return

        data = request.send()
        lines = chain.from_iterable(self._render_modifications(item, **kw) for item in data)
        print(*lines, sep='\n')

    @dry_run
    @login_retry
    @login_required
    def create(self, ask=False, batch=False, **kw):
        """Create an item on the service."""
        request = self.service.CreateRequest(params=kw)

        self.log_t(f"Creating {self.service.item.type}")
        self.log(request.options, prefix='')

        if ask or not batch:
            if not confirm(prompt=f'Submit {self.service.item.type}?', default=True):
                self.log('Creation aborted')
                return

        data = request.send()
        lines = self._render_create(data, **kw)
        print(*lines, sep='\n')

    @dry_run
    @login_retry
    def search(self, **kw):
        """Search for items on the service."""
        request = self.service.SearchRequest(params=kw)

        self.log(f'Searching for {self.service.item.type}s with the following options:')
        self.log_t(request.options, prefix='   - ')

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
        if isinstance(msg, (list, tuple)):
            if prefix:
                msg = (prefix + line for line in msg)
            if truncate:
                msg = (self._truncate(x) for x in msg)
            msg = '\n'.join(msg)
        else:
            msg = prefix + msg
            if truncate:
                msg = self._truncate(msg)

        if sys.stdout.isatty():
            output = sys.stdout
        else:
            output = sys.stderr

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

    def cache(self, *args, update=False, remove=False, **kw):
        if update:
            updates = self.service.cache_updates
            if updates != self.service.cache:
                self.service.cache.write(updates=updates)
        elif remove:
            self.service.cache.remove()

    def _render_modifications(self, data, **kw):
        raise NotImplementedError

    def _render_create(self, data, **kw):
        if data:
            yield f"Created {self.service.item.type} #{data}"

    def _render_search(self, data, fields=None, output=None, **kw):
        """Render search data for output."""
        if output is None:
            if fields is None:
                fields = ('id', 'owner', 'title')
                output = '{:<8} {:<20} {}'
            else:
                output = ' '.join('{}' for x in fields)

        for item in data:
            if output == '-':
                for field in fields:
                    try:
                        value = getattr(item, field)
                    except AttributeError:
                        raise BiteError(f'invalid field: {field!r}')
                    if value is None:
                        continue
                    if isinstance(value, (list, tuple)):
                        yield from map(str, value)
                    else:
                        yield str(value)
            else:
                values = (str(getattr(item, field)) for field in fields)
                yield output.format(*values)

    def _render_item(self, item, fields=None, **kw):
        """Render item data for output."""
        if fields is None:
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
        else:
            for field in fields:
                try:
                    value = getattr(item, field)
                except AttributeError:
                    raise BiteError(f'invalid field: {field!r}')
                if value is None:
                    continue
                if isinstance(value, (list, tuple)):
                    yield from map(str, value)
                else:
                    yield str(value)

    @dry_run
    @login_retry
    def changes(self, **kw):
        request = self.service.ChangesRequest(item_id=True, filtered=True, **kw)

        self.log('Getting changes matching the following options:')
        self.log_t(request.options, prefix='   - ')

        data = request.send()
        lines = self._render_events(data, **kw)
        print(*lines, sep='\n')

    @dry_run
    @login_retry
    def comments(self, **kw):
        """Get comments from a service."""
        request = self.service.CommentsRequest(item_id=True, filtered=True, **kw)

        self.log('Getting comments matching the following options:')
        self.log_t(request.options, prefix='   - ')

        data = request.send()
        lines = self._render_events(data, **kw)
        print(*lines, sep='\n')

    def _render_events(self, data, fields=None, output=None, **kw):
        if fields and output is None:
            output = ' '.join(['{}' for x in fields])

        for item_id, events in data:
            if output == '-':
                for event in events:
                    for field in fields:
                        try:
                            value = getattr(event, field)
                        except AttributeError:
                            raise BiteError(f'invalid field: {field!r}')
                        if value is None:
                            continue
                        if isinstance(value, list):
                            yield from map(str, value)
                        else:
                            yield value
            elif fields and output:
                for event in events:
                    values = (getattr(event, field, None) for field in fields)
                    yield from self._iter_lines(output.format(*values))
            else:
                events = list(str(x) for x in events)
                if events:
                    yield self._header('=', f'{self.service.item.type.capitalize()}: {item_id}')
                    yield from self._iter_lines(events)
