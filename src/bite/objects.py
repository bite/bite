from itertools import chain
import bz2
from datetime import datetime
import lzma
import os
import re
import stat
import zlib

try:
    # use uchardet bindings if available
    import cchardet as chardet
except ImportError:
    import chardet
from snakeoil import klass
from snakeoil.osutils import sizeof_fmt

from . import magic, const
from .exceptions import BiteError
from .utc import utc, parse_date


def decompress(fcn):
    """Decorator that decompresses returned data.

    libmagic is used to identify the MIME type of the data and the function
    will keep decompressing until no supported compression format is identified.
    """
    def wrapper(cls, raw=False, *args, **kw):
        data = fcn(cls)

        if raw:
            # return raw data without decompressing
            return data

        mime_type, mime_subtype = magic.from_buffer(data, mime=True).split('/')
        while mime_subtype in ('x-bzip2', 'x-bzip', 'bzip', 'x-gzip', 'gzip', 'x-xz'):
            if mime_subtype in ('x-bzip2', 'x-bzip', 'bzip'):
                data = bz2.decompress(data)
            elif mime_subtype in ('x-gzip', 'gzip'):
                data = zlib.decompress(data, 16 + zlib.MAX_WBITS)
            elif mime_subtype in ('x-xz'):
                data = lzma.decompress(data)
            mime_type, mime_subtype = magic.from_buffer(data, mime=True).split('/')
        return data
    return wrapper


class DateTime(object):
    """Object that converts/stores a given datetime object."""

    def __init__(self, datetime):
        # TODO: handle different time zones?
        self.token = datetime if isinstance(datetime, str) else None
        if self.token is not None:
            datetime = parse_date(datetime)
        self._datetime = datetime.replace(tzinfo=utc)

    def __str__(self):
        if self.token is not None:
            return f'{self.token!r} -- {self.local}'
        return self.local

    def __repr__(self):
        return repr(self._datetime)

    def isoformat(self, **kw):
        """Return a string representing the date and time in ISO 8601 format."""
        return self._datetime.isoformat(**kw)

    @property
    def utcformat(self):
        """Return a string representing the date and time in ISO 8601 format, assuming UTC."""
        return self._datetime.strftime('%Y-%m-%dT%H:%M:%SZ')

    @property
    def local(self):
        """Return datetime string converted to the system timezone."""
        return self._datetime.astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")

    def replace(self, **kw):
        """Return a modified datetime with kwargs specifying new attributes."""
        return self._datetime.replace(**kw)

    def strftime(self, fmt):
        """Return a modified datetime with kwargs specifying new attributes."""
        return self._datetime.strftime(fmt)

    def __eq__(self, x):
        return self._datetime == x

    def __gt__(self, x):
        return self._datetime > x

    def __ge__(self, x):
        return self._datetime >= x

    def __lt__(self, x):
        return self._datetime < x

    def __le__(self, x):
        return self._datetime <= x


class TimeInterval(object):
    """Object that converts/stores a given time interval."""

    def __init__(self, interval):
        # TODO: handle different time zones?
        self.token = interval if isinstance(interval, str) else None
        if self.token is not None:
            if not self.token:
                raise ValueError(f'invalid time interval: {interval!r}')
            start, _sep, end = interval.partition('/')
            start = parse_date(start) if start else None
            end = parse_date(end) if end else None
            interval = (start, end)
        # assume singular datetime obj input means that time or later
        elif isinstance(interval, datetime):
            interval = (interval, None)

        try:
            start, end = interval
        except ValueError:
            raise ValueError(f'invalid time interval: {interval!r}')

        self.start = DateTime(start) if start else start
        self.end = DateTime(end) if end else end

        if self.start and self.end and self.start > self.end:
            raise ValueError(
                'invalid time interval: start time after end time '
                f'({self.start} -> {self.end})')

    def __repr__(self):
        return repr((self.start, self.end))

    def __str__(self):
        l = []
        if self.token:
            l.extend((repr(self.token), '--'))

        if self.start and self.end:
            l.append(f'between {self.start} and {self.end}')
        elif self.start:
            l.append(f'after {self.start}')
        else:
            l.append(f'before {self.end}')

        return ' '.join(l)

    def __contains__(self, obj):
        if not isinstance(obj, datetime):
            return False
        if self.start is not None and obj < self.start:
            return False
        if self.end is not None and obj > self.end:
            return False
        return True

    def __iter__(self):
        return iter((self.start, self.end))


class IntRange(object):
    """Object that converts/stores a given integer range."""

    def __init__(self, interval):
        self.token = interval if isinstance(interval, str) else None
        if self.token is not None:
            if not self.token:
                raise ValueError(f'invalid range: {interval!r}')
            start, _sep, end = interval.partition('..')
            start = int(start) if start else None
            end = int(end) if end else None
            interval = (start, end)

        try:
            self.start, self.end = interval
        except ValueError:
            raise ValueError(f'invalid range: {interval!r}')

        if self.start and self.end and self.start > self.end:
            raise ValueError(
                'invalid range: start occurs after end '
                f'({self.start} -> {self.end})')

    def __repr__(self):
        return repr((self.start, self.end))

    def __str__(self):
        l = []
        if self.token:
            l.extend((repr(self.token), '--'))

        if self.start and self.end:
            l.append(f'between {self.start} and {self.end}')
        elif self.start:
            l.append(f'>= {self.start}')
        else:
            l.append(f'<= {self.end}')

        return ' '.join(l)

    def __iter__(self):
        return iter((self.start, self.end))


class Item(object):
    """Generic bug/issue/ticket object used by a service."""

    attributes = {}
    attribute_aliases = {}
    type = None

    _print_fields = (
        ('title', 'Title'),
        ('id', 'ID'),
        ('created', 'Reported'),
        ('modified', 'Updated'),
        ('comments', 'Comments'),
        ('attachments', 'Attachments'),
        ('changes', 'Changes'),
    )

    def __init__(self, id=None, title=None, creator=None, owner=None, created=None,
                 modified=None, status=None, url=None, blocks=None,
                 depends=None, cc=None, comments=None, attachments=None, changes=None, **kw):
        self.id = id # int
        self.title = title # string
        self.creator = creator # string
        self.owner = owner # string
        self.created = created # date object
        self.modified = modified # date object
        self.status = status # string
        self.url = url # string
        self.cc = cc # set
        self.blocks = blocks # set
        self.depends = depends # set
        self.comments = comments # list of Comment objects
        self.attachments = attachments # dict of lists of Attachment objects
        self.changes = changes # list of Change objects

    @klass.jit_attr
    def events(self):
        """Sorted list of all item events.

        Currently this relates to all comments and changes made to an item.
        """
        comments = self.comments if self.comments is not None else ()
        changes = self.changes if self.changes is not None else ()
        return sorted(chain(comments, changes), key=lambda event: event.created)

    def _custom_str_fields(self):
        """Custom field output for string rendering."""
        return ()

    def __str__(self):
        lines = []

        for field, title in self._print_fields:
            value = getattr(self, field, None)
            if value is None:
                continue

            if field in ('changes', 'comments', 'attachments'):
                value = len(value)

            # Initial comment is the description
            if field == 'comments': value -= 1

            if isinstance(value, (list, tuple)):
                value = ', '.join(map(str, value))

            lines.append(f'{title:<12}: {value}')

        lines.extend(sorted(self._custom_str_fields()))
        return '\n'.join(lines)

    def __getattr__(self, name):
        if name in self.attributes:
            return None
        elif name in self.attribute_aliases:
            return getattr(self, self.attribute_aliases[name])
        else:
            raise AttributeError(f'missing field: {name}')

    # allow items to be used as mapping args to functions
    def __getitem__(self, key):
        return self.__dict__[key]

    def keys(self):
        return self.__dict__.keys()


class Change(object):
    """Generic change event on a service."""

    change_aliases = {}

    def __init__(self, creator, created, changes, id=None, count=None):
        self.id = id # int
        self.creator = creator # string
        self.created = created # date object
        self.changes = changes # dict
        self.count = count # id

    def __str__(self):
        lines = [f'Change #{self.count} by {self.creator}, {self.created}']
        lines.append('-' * const.COLUMNS)
        for k, v in self.changes.items():
            try:
                removed, added = v
                if removed and added:
                    lines.append(f'{k.capitalize()}: {removed} -> {added}')
                elif removed:
                    lines.append(f'{k.capitalize()}: -{removed}')
                else:
                    lines.append(f'{k.capitalize()}: +{added}')
            except ValueError:
                lines.append(f'{k.capitalize()}: {v}')
        return '\n'.join(lines)

    def match(self, fields):
        for field in fields:
            if ':' in field:
                key, value = field.split(':')
            else:
                key = field
                value = None

            key = self.change_aliases.get(key, key)

            if not value:
                return key in self.changes
            else:
                try:
                    removed, added = self.changes[key]
                    if value.startswith('-'):
                        return removed == value[1:]
                    elif value.startswith('+'):
                        return added == value[1:]
                    else:
                        return value in self.changes[key]
                except KeyError:
                    return False
                except ValueError:
                    return value == self.changes[key]


class Comment(Change):
    """Generic comment on a service."""

    def __init__(self, creator, created, modified=None,
                 id=None, count=None, changes=None, text=None):
        self.modified = modified
        self.text = text
        super().__init__(id=id, creator=creator, created=created, changes=changes, count=count)

    def __str__(self):
        lines = []
        if self.count == 0:
            lines.append(f'Description by {self.creator}, {self.created}')
        else:
            lines.append(f'Comment #{self.count} by {self.creator}, {self.created}')
        lines.append('-' * const.COLUMNS)
        if self.text:
            lines.append(self.text)
        return '\n'.join(lines)

    @property
    def reply(self):
        lines = [f'In reply to {self.creator} from comment #{self.count}:']
        lines.extend(f'> {line}' for line in self.text.splitlines())
        return '\n'.join(lines)


class Attachment(object):
    """Generic attachment to an item on a service."""

    def __init__(self, id=None, filename=None, url=None, size=None,
                 mimetype=None, data=None, creator=None, created=None, modified=None):
        self.id = id
        # make sure the file name is valid
        # TODO: fix this to remove all os.path.sep chars
        self.filename = filename
        if self.filename is not None:
            self.filename = os.path.basename(re.sub(r'\.\.', '', self.filename))
        self.url = url
        self.size = size
        self.mimetype = mimetype
        self.data = data
        self.creator = creator
        self.created = created
        self.modified = modified

        # don't trust the content type -- users often set the wrong mimetypes
        if self.data is not None:
            mimetype = magic.from_buffer(self.read(), mime=True)
            if mimetype == 'application/octet-stream':
                # assume these are plaintext
                self.mimetype = 'text/plain'
            else:
                self.mimetype = mimetype

    def __str__(self):
        l = ['Attachment:']
        if self.id is not None:
            l.append(f'[ID: {self.id}]')
        l.append(f'[{self.filename}]')
        if self.size is not None:
            l.append(f'({sizeof_fmt(self.size)})')
        return ' '.join(l)

    @decompress
    def read(self):
        if isinstance(self.data, str):
            return self.data.encode()
        return self.data

    def write(self, path):
        try:
            with open(path, 'wb+') as f:
                os.chmod(path, stat.S_IREAD | stat.S_IWRITE)
                f.write(self.read(raw=True))
        except Exception as e:
            # toss file stub if it got created
            try:
                os.remove(path)
            except FileNotFoundError:
                pass

            if isinstance(e, IOError):
                raise BiteError(f'failed writing file: {path!r}: {e.strerror}')
            raise


class TarAttachment(object):
    def __init__(self, tarfile, cfile):
        self.tarfile = tarfile
        self.cfile = cfile

    @decompress
    def read(self):
        return self.tarfile.extractfile(self.cfile).read()

    def data(self):
        data = self.read()
        mime = magic.from_buffer(data, mime=True)
        if mime.startswith('text'):
            for encoding in ('utf-8', 'latin-1'):
                try:
                    return data.decode(encoding)
                except UnicodeDecodeError:
                    pass
            # fallback to detecting the encoding
            encoding = chardet.detect(data)['encoding']
            return data.decode(encoding)
        else:
            return 'Non-text data: ' + mime + '\n'
