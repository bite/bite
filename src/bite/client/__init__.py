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
from ..service import Service
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
            self.service.login(user, password)

    @login_retry
    def get(self, ids, dry_run=False, browser=False, output_url=False, **kw):
        """Get item(s) from a service and all related info."""
        if not ids:
            raise RuntimeError(f'No {self.service.item.type} ID(s) specified')

        def _item_urls(ids):
            if self.service.item_endpoint is None:
                raise BiteError(f"no web endpoint defined for {self.service.item.type}s")

            if self.service.item_endpoint.startswith('/'):
                item_url = self.service.webbase.rstrip('/') + self.service.item_endpoint
            else:
                item_url = self.service.item_endpoint

            for id in ids:
                yield item_url.format(id=id)

        if browser:
            urls = list(_item_urls(ids))
            self.log_t(f'Launching {self.service.item.type}{pluralism(ids)} in browser: {const.BROWSER}')
            self.log(urls, prefix='   - ')
            launch_browser(urls)
        elif output_url:
            print(*_item_urls(ids), sep='\n')
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
        self.log_t(f"{filename!r} attached to {self.service.item.type}{pluralism(ids)}: \
                   {', '.join(map(str, ids))}")

    def _attachment_urls(self, ids):
        if self.service.attachment_endpoint is None:
            raise BiteError("no web endpoint defined for attachments")

        if self.service.attachment_endpoint.startswith('/'):
            attachment_url = self.service.webbase.rstrip('/') + self.service.attachment_endpoint
        else:
            attachment_url = self.service.attachment_endpoint

        for id in ids:
            yield attachment_url.format(id=id)

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

        def _launch_browser(ids):
            urls = list(self._attachment_urls(ids))
            self.log_t(f'Launching attachment{pluralism(ids)} in browser: {const.BROWSER}')
            self.log(urls, prefix='   - ')
            launch_browser(urls)

        if not item_id and (output_url or browser):
            if output_url:
                print(*self._attachment_urls(ids), sep='\n')
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
                ids = (x.id for x in attachments)
                print(*self._attachment_urls(ids), sep='\n')
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
            sys.stdout.write(f.read().decode())

    def _save_attachment(self, f, path):
        """Save attachment to a specified path."""
        if os.path.exists(path):
            print(f' ! Warning: existing file: {path!r}')
            if not confirm('Do you want to overwrite it?'):
                return

        self.log(f'Saving attachment: {path!r}')
        f.write(path)

    @login_retry
    @login_required
    def modify(self, ask=False, dry_run=False, **kw):
        """Modify an item on the service."""
        request = self.service.ModifyRequest(**kw)
        ids = request.params['ids']

        self.log_t(f"Modifying {self.service.item.type}{pluralism(ids)}: {', '.join(map(str, ids))}")
        self.log(request.options, prefix='')

        if ask:
            if not confirm(prompt=f'Modify {self.service.item.type}{pluralism(ids)}?', default=True):
                self.log('Modification aborted')
                return

        if dry_run: return
        data = request.send()
        lines = chain.from_iterable(self._render_modifications(item, **kw) for item in data)
        print(*lines, sep='\n')

    @login_retry
    @login_required
    def create(self, ask=False, batch=False, dry_run=False, **kw):
        """Create an item on the service."""
        request = self.service.CreateRequest(**kw)

        self.log_t(f"Creating {self.service.item.type}")
        self.log(request.options, prefix='')

        if ask or not batch:
            if not confirm(prompt=f'Submit {self.service.item.type}?', default=True):
                self.log('Creation aborted')
                return

        if dry_run: return
        data = request.send()
        lines = self._render_create(data, **kw)
        print(*lines, sep='\n')

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
        if isinstance(msg, (list, tuple)):
            if prefix:
                msg = [prefix + line if i > 0 else line for i, line in enumerate(msg)]
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

    def changes(self, ids, dry_run=False, **kw):
        change_num = kw.get('change_num', None)
        creator = kw.get('creator', None)
        creation_time = kw.get('creation_time', None)
        match = kw.get('match', None)

        request = self.service.ChangesRequest(
            ids=ids, item_id=True, created=kw.get('creation_time', None))

        if creator is not None:
            request.options.append(f"Creator{pluralism(creator)}: {', '.join(creator)}")
        if change_num is not None:
            request.options.append(
                f"Change number{pluralism(change_num)}: {', '.join(map(str, change_num))}")
        if match is not None:
            request.options.append(f"Matching: {', '.join(match)}")

        self.log('Getting changes matching the following options:')
        self.log_t(request.options, prefix='   - ')

        if kw.get('creator', None) is not None and self.service.suffix is not None:
            kw['creator'] = list(map(self.service._resuffix, kw['creator']))

        if dry_run: return
        changes = request.send()
        lines = chain.from_iterable(self._render_changes(ids[i], change, **kw)
                                    for i, change in enumerate(changes))
        print(*lines, sep='\n')

    def _render_changes(self, item_id, changes, creation_time=None, change_num=None,
                        fields=None, output=None, creator=None, match=None, **kw):
        if creator is not None:
            changes = (x for x in changes if x.creator in creator)
        if creation_time is not None:
            changes = (x for x in changes if x.created >= creation_time)
        if match is not None:
            changes = (event for event in changes if event.match(fields=match))
        if change_num is not None:
            if len(change_num) == 1 and change_num[0] < 0:
                changes = list(changes)[change_num[0]:]
            else:
                changes = (x for x in changes if x.count in change_num)

        if fields and output is None:
            output = ' '.join(['{}' for x in fields])

        if output == '-':
            for change in changes:
                for field in fields:
                    try:
                        value = getattr(change, field)
                    except AttributeError:
                        raise BiteError(f'invalid field: {field!r}')
                    if value is None:
                        continue
                    if isinstance(value, list):
                        yield from map(str(value))
                    else:
                        yield value
        elif fields and output:
            for change in changes:
                values = (getattr(change, field, None) for field in fields)
                yield from self._iter_lines(output.format(*values))
        else:
            changes = list(str(x) for x in changes)
            if changes:
                yield self._header('=', f'{self.service.item.type.capitalize()}: {item_id}')
                yield from self._iter_lines(changes)

    def comments(self, ids, dry_run=False, **kw):
        creation_time = kw.get('creation_time', None)
        creator = kw.get('creator', None)
        attachment = kw.get('attachment', False)
        comment_num = kw.get('comment_num', None)

        request = self.service.CommentsRequest(
            ids=ids, item_id=True, created=creation_time)

        if creator is not None:
            request.options.append(f"Creator{pluralism(creator)}: {', '.join(creator)}")
        if attachment:
            request.options.append('Attachments: yes')
        if comment_num is not None:
            request.options.append(
                f"Comment number{pluralism(comment_num)}: {', '.join(map(str, comment_num))}")

        self.log('Getting comments matching the following options:')
        self.log_t(request.options, prefix='   - ')

        if self.service.suffix is not None and creator is not None:
            creator = list(map(self.service._resuffix, creator))

        if dry_run: return
        comments_iter = request.send()
        lines = chain.from_iterable(self._render_comments(ids[i], comments, **kw)
                                    for i, comments in enumerate(comments_iter))
        print(*lines, sep='\n')

    def _render_comments(self, item_id, comments, creation_time=None, comment_num=None,
                        fields=None, output=None, creator=None, attachment=False, **kw):
        if creator is not None:
            comments = (x for x in comments if x.creator in creator)
        if attachment:
            comments = (x for x in comments if x.changes['attachment_id'] is not None)
        if comment_num is not None:
            if any(x < 0 for x in comment_num):
                comments = list(comments)
                selected = []
                for x in comment_num:
                    try:
                        selected.append(comments[x])
                    except IndexError:
                        pass
                comments = selected
            else:
                comments = (x for x in comments if x.count in comment_num)

        if fields and output is None:
            output = ' '.join(['{}' for x in fields])

        if output == '-':
            for comment in comments:
                for field in fields:
                    try:
                        value = getattr(comment, field)
                    except AttributeError:
                        raise BiteError(f'invalid field: {field!r}')
                    if value is None:
                        continue
                    if isinstance(value, list):
                        yield from map(str, value)
                    else:
                        yield value
        elif fields and output:
            for comment in comments:
                values = (getattr(comment, field, None) for field in fields)
                yield from self._iter_lines(output.format(*values))
        else:
            comments = list(str(x) for x in comments)
            if comments:
                yield self._header('=', f'{self.service.item.type.capitalize()}: {item_id}')
                yield from self._iter_lines(comments)
