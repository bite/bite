"""Support Monorail's (Google Code issue tracker) API.

API docs:
    https://chromium.googlesource.com/infra/infra/+/master/appengine/monorail/doc/api.md
    https://apis-explorer.appspot.com/apis-explorer/?base=https://monorail-prod.appspot.com/_ah/api#p/monorail/v1/
"""

from itertools import chain
import re
from types import GeneratorType
from urllib.parse import urlparse

try: import simplejson as json
except ImportError: import json
from lxml import etree
import lxml.html

from ._jsonrpc import Jsonrpc
from ..objects import decompress, Item, Comment, Attachment
from ..exceptions import RequestError, AuthError, BadAuthToken
from .._vendor.rfc3339 import parse_datetime as parsetime


class Monorail(Jsonrpc):
    """Service supporting Monorail (Google Code issue tracker)."""

    #_service = 'monorail'

    def __init__(self, base, max_results=None, **kw):
        try:
            api_base, project = base.split('/p/', 1)
            project = project.rstrip('/')
        except ValueError as e:
            raise BiteError(f'invalid project base: {base!r}')

        monorail_base = 'https://monorail-prod.appspot.com/_ah/api/monorail/v1/projects'

        if max_results is None:
            max_results = 1000
        super().__init__(
            endpoint=f'/{project}', base=base, max_results=max_results, **kw)
        self.webbase = base


class GooglecodeIssue(Item):

    attributes = {
        #'cc': 'CC',
        #'label': 'Labels',
        #'summary': 'Summary',
        #'updates': 'Updates',

        # available via search
        'id': 'ID',
        'title': 'Title',
        'url': 'URL',
        'reporter': 'Reporter',
        'opened': 'Opened',
        'modified': 'Updated',
        'owner': 'Owner',
        'status': 'Status',
        'state': 'State',
        'stars': 'Stars',
    }

    attribute_aliases = {
        'created': 'opened',
    }

    type = 'issue'

    def __init__(self, labels=None, stars=0, state=None, **kw):
        self.labels = labels
        self.stars = stars
        self.state = state
        super().__init__(**kw)

    def __str__(self):
        lines = []
        print_fields = [
            ('title', 'Title'),
            ('reporter', 'Reporter'),
            ('opened', 'Reported'),
            ('modified', 'Updated'),
            ('owner', 'Owner'),
            ('status', 'Status'),
            ('state', 'State'),
            ('stars', 'Stars'),
            ('cc', 'CC'),
            ('blocks', 'Blocks'),
            ('depends', 'Depends'),
            ('labels', 'Labels'),
            ('url', 'URL'),
        ]

        for field, title in print_fields:
            value = getattr(self, field)

            if field == 'labels':
                attr = re.compile(r'^(.+)-(.+)$')
                for label in value:
                    x = attr.match(label)
                    if x:
                        lines.append('{:<12}: {}'.format(x.group(1), x.group(2)))
                    else:
                        lines.append('{:<12}: {}'.format('Label', label))
                continue

            if isinstance(value, list) or isinstance(value, GeneratorType):
                value = ', '.join(map(str, value))

            if not value:
                continue
            else:
                lines.append('{:<12}: {}'.format(title, value))

        return '\n'.join(lines)


class GooglecodeComment(Comment):
    def __init__(self, id=None, creator=None, created=None, count=None, changes=None, text=None, **kw):
        if not text:
            text = '(No comment was entered for this change)'
        super().__init__(id, creator, created, count, changes, text)
