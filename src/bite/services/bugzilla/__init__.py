import base64
import datetime
import re
import string

from dateutil.parser import parse as dateparse

from .. import Service, Request
from ... import const, utc
from ...cache import Cache, csv2tuple
from ...exceptions import RequestError, AuthError
from ...objects import Item, Change, Comment, Attachment, decompress


class BugzillaError(RequestError):

    def __init__(self, msg, code=None, text=None):
        msg = 'Bugzilla error: ' + msg
        super().__init__(msg, code, text)


def parsetime(time):
    if not isinstance(time, datetime.datetime):
        return dateparse(str(time))
    else:
        return time.replace(tzinfo=utc.utc)


class BugzillaCache(Cache):

    def __init__(self, *args, **kw):
        # default to bugzilla-5 open/closed statuses
        defaults = {
            'open_status': ('CONFIRMED', 'IN_PROGRESS', 'UNCONFIRMED'),
            'closed_status': ('RESOLVED', 'VERIFIED'),
        }

        converters = {
            'open_status': csv2tuple,
            'closed_status': csv2tuple,
        }

        super().__init__(defaults=defaults, converters=converters, *args, **kw)


class Bugzilla(Service):

    def __init__(self, restrict_login=False, **kw):
        self.restrict_login = restrict_login
        super().__init__(cache_cls=BugzillaCache, **kw)

        self.item = BugzillaBug
        self.attachment = BugzillaAttachment

        # TODO: temporary compat
        self.attributes = self.item.attributes
        self.attribute_aliases = self.item.attribute_aliases

    @property
    def cache_updates(self):
        """Pull latest data from service for cache update."""
        config_updates = {}
        reqs = []

        # get open/closed status values
        reqs.append(self.FieldsRequest(names=['bug_status']))
        # get server bugzilla version
        reqs.append(self.VersionRequest())

        statuses, version = self.send(reqs)

        open_status = []
        closed_status = []
        for status in statuses[0].get('values', []):
            if status.get('name', None) is not None:
                if status.get('is_open', False):
                    open_status.append(status['name'])
                else:
                    closed_status.append(status['name'])
        config_updates['open_status'] = tuple(sorted(open_status))
        config_updates['closed_status'] = tuple(sorted(closed_status))
        config_updates['version'] = version

        return config_updates

    def inject_auth(self, request, params):
        if params is None:
            params = {}
        # TODO: Is there a better way to determine the difference between
        # tokens and API keys?
        if len(self.auth) > 16:
            params['Bugzilla_api_key'] = str(self.auth)
        else:
            params['Bugzilla_token'] = str(self.auth)
        return request, params

    def query(self, method, params=None):
        """Query bugzilla for various data."""
        req = self.create_request(method=method, params=params)
        data = self.send(req)
        return data

    def _failed_http_response(self, response):
        if response.status_code in (401, 403):
            data = self.parse_response(response)
            raise AuthError('authentication failed: {}'.format(data.get('message', '')))
        else:
            super()._failed_http_response(response)


class ExtensionsRequest(Request):

    def parse(self, data):
        return data['extensions']


class VersionRequest(Request):

    def parse(self, data):
        return data['version']


class FieldsRequest(Request):

    def __init__(self, ids=None, names=None, **kw):
        """Get information about valid bug fields.

        :param ids: fields IDs
        :type ids: list of ints
        :param names: field names
        :type names: list of strings

        """
        params = {}
        options_log = []

        if ids is None and names is None:
            options_log.append('all non-obsolete fields')

        if ids is not None:
            ids = list(map(str, ids))
            params['ids'] = ids
            options_log.append('IDs: {}'.format(', '.join(ids)))
        if names is not None:
            params['names'] = names
            options_log.append('Field names: {}'.format(', '.join(names)))

        super().__init__(params=params, **kw)
        self.options = options_log

    def parse(self, data):
        return data['fields']


class UsersRequest(Request):

    def __init__(self, ids=None, names=None, match=None, **kw):
        """Query bugzilla for user data."""
        if not any((ids, names, match)):
            raise ValueError('No user ID(s), name(s), or match(es) specified')

        params = {}
        options_log = []

        if ids is not None:
            ids = list(map(str, ids))
            params['ids'] = ids
            options_log.append('IDs: {}'.format(', '.join(ids)))
        if names is not None:
            params['names'] = names
            options_log.append('Login names: {}'.format(', '.join(names)))
        if match is not None:
            params['match'] = match
            options_log.append('Match patterns: {}'.format(', '.join(match)))

        super().__init__(params=params, **kw)
        self.options = options_log

    def parse(self, data):
        return data['users']


class BugzillaBug(Item):

    attributes = {
        'actual_time': 'Actual time',
        'alias': 'Alias',
        'assigned_to': 'Assignee',
        'attachments': 'Attachments',
        'blocks': 'Blocks',
        'cc': 'CC',
        'classification': 'Classification',
        'comments': 'Comments',
        'component': 'Component',
        'creation_time': 'Created',
        'creator': 'Reporter',
        'deadline': 'Deadline',
        'depends_on': 'Depends',
        'dupe_of': 'Duplicate of',
        'estimated_time': 'Estimated time',
        'flags': 'Flags',
        'groups': 'Groups',
        'history': 'History',
        'id': 'ID',
        'is_cc_accessible': 'Is CC Accessible',
        'is_confirmed': 'Confirmed',
        'is_creator_accessible': 'Is Creator Accessible',
        'keywords': 'Keywords',
        'last_change_time': 'Modified',
        'op_sys': 'Operating System',
        'platform': 'Platform',
        'priority': 'Priority',
        'product': 'Product',
        'qa_contact': 'QA Contact',
        'ref': 'Reference',
        'remaining_time': 'Remaining time',
        'resolution': 'Resolution',
        'see_also': 'See also',
        'severity': 'Severity',
        'status': 'Status',
        'summary': 'Title',
        'target_milestone': 'Target milestone',
        'url': 'URL',
        'version': 'Version',
        'whiteboard': 'Whiteboard',
    }

    attribute_aliases = {
        'owner': 'assigned_to',
        'modified': 'last_change_time',
        'created': 'creation_time',
        'depends': 'depends_on',
        'title': 'summary'
    }

    endpoint = '/show_bug.cgi?id='
    type = 'bug'

    def __init__(self, service, bug, comments=None, attachments=None, history=None, **kw):
        self.service = service
        for k, v in bug.items():
            if not v or v == '---':
                # skip empty lists and blank fields
                continue
            elif v == 'flags':
                self.flags = [flag['name'] for flag in bug['flags']]
            elif k in ['creation_time', 'last_change_time']:
                setattr(self, k, parsetime(v))
            else:
                if isinstance(v, str) and re.match(r'^\d\d\d\d-\d\d-\d\dT\d\d:\d\d:\d\dZ$', v):
                    setattr(self, k, parsetime(v))
                else:
                    setattr(self, k, v)

        if attachments:
            self.attachments = attachments
        if comments:
            self.comments = comments
        if history:
            self.history = history

    def __str__(self):
        lines = []
        print_fields = [
            ('summary', 'Title'),
            ('alias', 'Alias'),
            ('assigned_to', 'Assignee'),
            ('creator', 'Reporter'),
            ('qa_contact', 'QA Contact'),
            ('creation_time', 'Reported'),
            ('last_change_time', 'Updated'),
            ('status', 'Status'),
            ('resolution', 'Resolution'),
            ('dupe_of', 'Duplicate'),
            ('whiteboard', 'Whiteboard'),
            ('severity', 'Severity'),
            ('priority', 'Priority'),
            ('classification', 'Class'),
            ('product', 'Product'),
            ('component', 'Component'),
            ('platform', 'Platform'),
            ('op_sys', 'OS'),
            ('keywords', 'Keywords'),
            ('target_milestone', 'Target'),
            ('version', 'Version'),
            ('url', 'URL'),
            ('ref', 'Reference'),
            ('see_also', 'See also'),
            ('cc', 'CC'),
            ('id', 'ID'),
            ('blocks', 'Blocks'),
            ('depends_on', 'Depends'),
            ('flags', 'Flags'),
            ('groups', 'Groups'),
            ('estimated_time', 'Estimated'),
            ('deadline', 'Deadline'),
            ('actual_time', 'Actual'),
            ('remaining_time', 'Remaining'),
            #('is_cc_accessible', 'Is CC Accessible'),
            #('is_confirmed', 'Confirmed'),
            #('is_creator_accessible', 'Is Creator Accessible'),
            ('history', 'Changes'),
            ('comments', 'Comments'),
            ('attachments', 'Attachments'),
        ]

        for field, title in print_fields:
            value = getattr(self, field)
            if value is None:
                continue

            if field in ['history', 'comments', 'attachments']:
                value = len(value)

            # Initial comment is the bug description
            if field == 'comments': value -= 1

            if isinstance(value, list):
                value = ', '.join(map(str, value))

            lines.append('{:<12}: {}'.format(title, value))

        custom_fields = ((k, v) for (k, v) in vars(self).items()
                         if re.match(r'^cf_\w+$', k))
        for k, v in custom_fields:
            if isinstance(v, list):
                value = ', '.join(v)
            else:
                value = v
            title = string.capwords(k[3:], '_')
            title = title.replace('_', ' ')
            lines.append('{:<12}: {}'.format(title, value))

        return '\n'.join(lines)

    def __getattribute__(self, name):
        value = object.__getattribute__(self, name)
        if name == 'cc' and isinstance(value, list):
            return list(map(self.service._desuffix, value))
        elif isinstance(value, str):
            return self.service._desuffix(value)
        else:
            return value

    def __getattr__(self, name):
        if name in self.attributes.keys():
            return None
        else:
            raise AttributeError

class BugzillaComment(Comment):
    def __init__(self, comment, id, count, rest=False, **kw):
        self.comment_id = comment['id']

        if rest:
            if 'real_name' in comment['creator'] and comment['creator']['real_name'] != '':
                creator = '{} ({})'.format(comment['creator']['real_name'], comment['creator']['name'])
            else:
                creator = comment['creator']['name']
        else:
            creator = comment['creator']

        date = parsetime(comment['creation_time'])
        count = comment['count']

        if comment['text'] is None:
            text = None
        else:
            text = comment['text'].strip()

        changes = {}
        if 'attachment_id' in comment:
            changes['attachment_id'] = comment['attachment_id']

        super().__init__(
            id=id, creator=creator, date=date,
            count=count, changes=changes, text=text)

class BugzillaEvent(Change):
    def __init__(self, change, id, alias=None, count=None, rest=False, **kw):
        self.alias = alias
        if rest:
            creator = change['changer']['name']
            date = parsetime(change['change_time'])
        else:
            creator = change['who']
            date = parsetime(change['when'])
        changes = change['changes']
        super().__init__(
            creator=creator, date=date, id=id,
            changes=changes, count=count)

    def __str__(self):
        change_fields = {
            'attachments.isobsolete': 'Obsolete attachment',
            'attachments.ispatch': 'Patch attachment',
            'attachments.description': 'Attachment description',
            'attachments.filename': 'Attachment filename',
            'attachments.mimetype': 'Attachment mimetype',
            'blocked': 'Blocks',
            'bug_file_loc': 'URL',
            'bug_group': 'Group',
            'bug_severity': 'Severity',
            'bug_status': 'Status',
            'cclist_accessible': 'CCs accessible',
            'dependson': 'Depends',
            'everconfirmed': 'Confirmed',
            'flag': 'Flag',
            'flagtypes.name': 'Flag type name',
            'rep_platform': 'Platform',
            'reporter_accessible': 'Reporter accessible',
            'short_desc': 'Title',
            'status_whiteboard': 'Whiteboard',
        }
        change_fields.update(BugzillaBug.attributes)

        lines = ['Change #{} by {}, {}'.format(self.count, self.creator, self.date)]
        lines.append('-' * const.COLUMNS)
        for change in self.changes:
            try:
                field = change_fields[change['field_name']]
            except KeyError:
                field = change['field_name']
                if re.match(r'^cf_\w+$', field):
                    field = string.capwords(field[3:], '_')
                    field = field.replace('_', ' ')

            if change['field_name'] == 'attachments.isobsolete':
                lines.append('{}: {}'.format(field, change['attachment_id']))
            else:
                if change['removed'] and change['added']:
                    changes = '{} -> {}'.format(change['removed'], change['added'])
                elif change['removed']:
                    changes = ', '.join(['-' + c for c in change['removed'].split(', ')])
                elif change['added']:
                    changes = ', '.join(['+' + c for c in change['added'].split(', ')])
                lines.append('{}: {}'.format(field, changes))

        return '\n'.join(lines)

class BugzillaAttachment(Attachment):

    endpoint = '/attachment.cgi?id='

    def __init__(self, id, file_name, size=None, content_type=None,
                 data=None, creation_time=None, last_change_time=None, **kw):

        if creation_time is not None:
            creation_time = parsetime(creation_time)
        if last_change_time is not None:
            last_change_time = parsetime(last_change_time)

        for k, v in kw.items():
            setattr(self, k, v)

        super().__init__(
            id=id, filename=file_name, size=size, mimetype=content_type,
            data=data, created=creation_time, modified=last_change_time)

    def __str__(self):
        if self.size is not None:
            if self.size < 1024*1024:
                size = '{}K'.format(round(self.size / 1024.0, 2))
            else:
                size = '{}M'.format(round(self.size / 1024*1024.0, 2))

            return 'Attachment: [{}] [{}] ({}, {})'.format(self.id, self.summary, size, self.mimetype)
        else:
            return 'Attachment: [{}] [{}]'.format(self.id, self.summary)

    @decompress
    def read(self):
        return base64.b64decode(self.data)
