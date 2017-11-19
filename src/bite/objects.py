from itertools import chain
import bz2
import lzma
import os
import re
import sys
import stat
import tarfile
import zlib

try:
    import cchardet as chardet
except ImportError:
    import chardet

from . import magic, const
from .utc import utc


def decompress(fcn):
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
                data = zlib.decompress(data, 16+zlib.MAX_WBITS)
            elif mime_subtype in ('x-xz'):
                data = lzma.decompress(data)
            mime_type, mime_subtype = magic.from_buffer(data, mime=True).split('/')
        return data
    return wrapper

def flatten(list_of_lists):
    "Flatten one level of nesting"
    return list(chain.from_iterable(list_of_lists))


class DateTime(object):

    def __init__(self, token, datetime):
        self.token = token
        self._datetime = datetime.replace(tzinfo=utc)

    def __str__(self):
        return str(self._datetime)

    @property
    def format(self):
        """Format the service expects datetime objects sent to it in."""
        return self._datetime.isoformat()

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


class PrintableObject(object):
    def __str__(self):
        raise NotImplemented

    def __str__(self):
        return str(self).encode('utf-8')


class Item(PrintableObject):

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


class Change(PrintableObject):
    def __init__(self, creator, date, changes, id=None, count=None):
        self.id = id # int
        self.creator = creator # string
        self.date = date # date object
        self.changes = changes # dict
        self.count = count # id

    def __str__(self):
        return f'Change by {self.creator}, {self.date}'

class Comment(Change):
    def __init__(self, creator, date, id=None, count=None, changes=None, text=None):
        self.text = text
        super().__init__(id=id, creator=creator, date=date, changes=changes, count=count)

    def __str__(self):
        if self.count == 0:
            lines = [f'Description by {self.creator}, {self.date}']
        else:
            lines = [f'Comment #{self.count} by {self.creator}, {self.date}']
        lines.append('-' * const.COLUMNS)
        if self.text:
            lines.append(self.text)
        return '\n'.join(lines)

class Attachment(PrintableObject):

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
        if self.size is not None:
            return f'Attachment: [{self.id}] [{self.filename}] ({self.size})'
        else:
            return f'Attachment: [{self.id}] [{self.filename}]'

    @decompress
    def read(self):
        if isinstance(self.data, str):
            return self.data.encode()
        return self.data

    def write(self, path):
        with open(path, 'wb+') as f:
            os.chmod(path, stat.S_IREAD | stat.S_IWRITE)
            f.write(self.read(raw=True))


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
