import base64
import codecs
import datetime
from functools import partial
from itertools import groupby
import os
import re
import string
import sys

from dateutil.parser import parse as dateparse

from bite import magic, utc
from bite.objects import Item, Change, Comment, Attachment, decompress
from bite.services import Service, Request, NullRequest

def parsetime(time):
    if not isinstance(time, datetime.datetime):
        return dateparse(time)
    else:
        return time.replace(tzinfo=utc.utc)

class SearchRequest(Request):
    def __init__(self, service, *args, **kw):
        """Construct a search request."""
        super(SearchRequest, self).__init__(service)
        method = 'Bug.search'

        params = {}
        options_log = []
        for k, v in ((k, v) for (k, v) in kw.items() if v):
            if k in BugzillaBug.attributes:
                if k in ['creation_time', 'last_change_time']:
                    params[k] = v[1]
                    options_log.append('{}: {} (since {} UTC)'.format(BugzillaBug.attributes[k], v[0], parsetime(v[1])))
                elif k in ['assigned_to', 'creator']:
                    params[k] = list(map(self.service._resuffix, v))
                    options_log.append('{}: {}'.format(BugzillaBug.attributes[k], ', '.join(map(str, v))))
                elif k == 'status':
                    params[k] = []
                    status_alias = []
                    for status in v:
                        if status.lower() == 'all':
                            status_alias.append(status)
                            params[k].extend(['UNCONFIRMED', 'NEW', 'CONFIRMED', 'ASSIGNED', 'IN_PROGRESS', 'REOPENED', 'RESOLVED', 'VERIFIED'])
                        elif status.lower() == 'open':
                            status_alias.append(status)
                            params[k].extend(['UNCONFIRMED', 'NEW', 'CONFIRMED', 'ASSIGNED', 'IN_PROGRESS', 'REOPENED'])
                        elif status.lower() == 'closed':
                            status_alias.append(status)
                            params[k].extend(['RESOLVED', 'VERIFIED'])
                        else:
                            params[k].append(status)
                    if status_alias:
                        options_log.append('{}: {} ({})'.format(BugzillaBug.attributes[k], ', '.join(status_alias), ', '.join(params[k])))
                    else:
                        options_log.append('{}: {}'.format(BugzillaBug.attributes[k], ', '.join(params[k])))
                else:
                    params[k] = v
                    options_log.append('{}: {}'.format(BugzillaBug.attributes[k], ', '.join(map(str, v))))
            else:
                if k == 'terms':
                    params['summary'] = v
                    options_log.append('{}: {}'.format('Summary', ', '.join(map(str, v))))
                elif k in ['limit', 'offset']:
                    params[k] = v

        if not params:
            raise ValueError('No search terms or options specified')

        if not 'status' in params:
            params['status'] = ['UNCONFIRMED', 'NEW', 'CONFIRMED', 'ASSIGNED', 'IN_PROGRESS', 'REOPENED']

        if not 'fields' in kw or kw['fields'] is None:
            fields = ['id', 'assigned_to', 'summary']
        else:
            fields = kw['fields']
            options_log.append('{}: {}'.format('Fields', ' '.join(fields)))

        # TODO: only supported >=3.6
        params['include_fields'] = fields

        self.fields = fields
        self.options = options_log

        self.request = self.service.create_request(method, params)

    def parse(self, data, *args, **kw):
        bugs = data['bugs']
        return (self.service.bug(service=self.service, bug=bug) for bug in bugs)

class CommentsRequest(Request):
    def __init__(self, service, ids, comment_ids=None, created=None, fields=None, *args, **kw):
        """Construct a comments request."""
        super(CommentsRequest, self).__init__(service, *args, **kw)
        method = 'Bug.comments'

        self.ids = ids
        if self.ids is None:
            raise ValueError('No bug ID(s) specified')
        params = {'ids': self.ids}
        if comment_ids is not None:
            params['comment_ids'] = comment_ids
        if created is not None:
            params['new_since'] = created
        if fields is not None:
            params['include_fields'] = fields

        # TODO: this
        self.options = ['REPLACE ME']

        self.request = self.service.create_request(method, params)

    def parse(self, data, *args, **kw):
        bugs = data['bugs']
        for i in self.ids:
            yield [BugzillaComment(comment=comment, id=i, count=j) for j, comment in enumerate(bugs[str(i)]['comments'])]

class ChangesRequest(Request):
    pass

class GetRequest(Request):
    def __init__(self, service, ids, fields=None, *args, **kw):
        """Construct a get request."""
        super(GetRequest, self).__init__(service)
        if not ids:
            raise ValueError('No bug ID(s) specified')
        method = 'Bug.get'
        params = {}
        params['permissive'] = True
        params['ids'] = ids
        if fields is not None:
            params['include_fields'] = fields
        self.request = self.service.create_request(method, params)

    def parse(self, data):
        return data['bugs']

class ModifyRequest(Request):
    def __init__(self, service, ids, *args, **kw):
        """Construct a modify request."""
        super(ModifyRequest, self).__init__(service)

        options_log = []
        params = {}
        for k, v in ((k, v) for (k, v) in kw.items() if v):
            if k in BugzillaBug.attributes:
                if k == 'assigned_to':
                    v = self.service._resuffix(v)
                params[k] = v
                options_log.append('{:<10}: {}'.format(BugzillaBug.attributes[k], v))
            elif '-' in k:
                keys = k.split('-')
                if len(keys) != 2:
                    raise RuntimeError('Argument parsing error')
                else:
                    if keys[0] == 'cc':
                        v = list(map(self.service._resuffix, v))
                    if k == 'comment-body':
                        v = codecs.getdecoder('unicode_escape')(v)[0]

                    if keys[0] not in kw:
                        params[keys[0]] = {}

                    params[keys[0]][keys[1]] = v

                    if keys[1] in ['add', 'remove', 'set']:
                        options_log.append((keys[0], keys[1], v))
                    elif keys[0] == 'comment':
                        pass
                    else:
                        try:
                            options_log.append('{:<10}: {}'.format(BugzillaBug.attributes[keys[0]], v))
                        except KeyError:
                            options_log.append('{:<10}: {}'.format(keys[0].capitalize(), v))
            else:
                if k == 'fixed':
                    params['status'] = 'RESOLVED'
                    params['resolution'] = 'FIXED'
                    options_log.append('Status    : RESOLVED')
                    options_log.append('Resolution: FIXED')
                elif k == 'invalid':
                    params['status'] = 'RESOLVED'
                    params['resolution'] = 'INVALID'
                    options_log.append('Status    : RESOLVED')
                    options_log.append('Resolution: INVALID')

        merge_targets = ((i, x) for i, x in enumerate(options_log) if isinstance(x, tuple))
        merge_targets = sorted(merge_targets, key=lambda x: x[1][0])
        old_indices = [i for (i, x) in merge_targets]
        for key, group in groupby(merge_targets, lambda x: x[1][0]):
            value = []
            for (_, (key, action, values)) in group:
                if action == 'add':
                    value.extend(['+' + str(x) for x in values])
                elif action == 'remove':
                    value.extend(['-' + str(x) for x in values])
                elif action == 'set':
                    value = values
                    break
            try:
                options_log.append('{:<10}: {}'.format(BugzillaBug.attributes[key], ', '.join(value)))
            except KeyError:
                options_log.append('{:<10}: {}'.format(key.capitalize(), ', '.join(value)))

        # remove old entries
        options_log = [x for i, x in enumerate(options_log) if i not in old_indices]

        if not params:
            raise ValueError('No changes specified')

        if options_log:
            prefix = '--- Modifying fields '
            options_log.insert(0, prefix + '-' * 10)

        if 'comment' in params:
            prefix = '--- Adding comment '
            options_log.append(prefix + '-' * 10)
            options_log.append(params['comment']['body'])

        options_log.append('-' * 10)

        self.options = options_log

        if not ids:
            raise ValueError('No bug ID(s) specified')
        params['ids'] = ids
        method = 'Bug.update'
        self.request = self.service.create_request(method, params)

    def parse(self, data, *args, **kw):
        return data['bugs']

class CreateRequest(Request):
    pass

class AttachRequest(Request):
    pass

class AttachmentsRequest(Request):
    def __init__(self, service, ids, fields=None, *args, **kw):
        """Construct a attachments request."""
        super(AttachmentsRequest, self).__init__(service, *args, **kw)
        method = 'Bug.attachments'
        if not ids:
            raise ValueError('No bug ID(s) specified')
        params = {'ids': ids, 'exclude_fields': ['data']}
        if fields is not None:
            params['include_fields'] = fields
        self.request = self.service.create_request(method, params)

        # TODO: this
        self.options = ['REPLACE ME']

        self.ids = ids

    def parse(self, data, *args, **kw):
        bugs = data['bugs']
        for i in self.ids:
            yield [self.service.attachment(**attachment) for attachment in bugs[str(i)]]

class HistoryRequest(Request):
    def __init__(self, service, ids, *args, **kw):
        super(HistoryRequest, self).__init__(service, *args, **kw)
        method = 'Bug.history'
        if not ids:
            raise ValueError('No bug ID(s) specified')
        params = {'ids': ids}
        self.request = self.service.create_request(method, params)

        # TODO: this
        self.options = ['REPLACE ME']

    def parse(self, data, *args, **kw):
        bugs = data['bugs']
        for b in bugs:
            yield [BugzillaEvent(change=x, id=b['id'], alias=b['alias'], count=i) for i, x in enumerate(b['history'], start=1)]

class Bugzilla(Service):
    def __init__(self, **kw):
        self.item = 'bug'
        super(Bugzilla, self).__init__(**kw)

        self.attachment = BugzillaAttachment
        self.bug = BugzillaBug

        # TODO: temporary compat
        self.attributes = self.bug.attributes
        self.attribute_aliases = self.bug.attribute_aliases

    def login(self, user=None, password=None):
        """Authenticate a session."""
        super(Bugzilla, self).login(user, password)

        method = 'User.login'
        params = {'login': user, 'password': password}
        req = self.create_request(method, params)

        content = self.send(req)
        self.auth_token = content['token']

    def add_attachment(self, ids, data=None, filepath=None, filename=None, mimetype=None,
                       is_patch=False, is_private=False, comment=None, summary=None, **kw):
        """Add an attachment to a bug

        :param ids: The ids or aliases of bugs that you want to add the attachment to.
        :type ids: list of ints and/or strings
        :param data: Raw attachment data
        :type data: binary data
        :param filepath: Path to the file.
        :type filepath: string
        :param filename: The file name that will be displayed in the UI for the attachment.
        :type filename: string
        :param mimetype: The MIME type of the attachment, like text/plain or image/png.
        :type mimetype: string
        :param comment: A comment to add along with the attachment.
        :type comment: string
        :param summary: A short string describing the attachment.
        :type summary: string
        :param is_patch: True if Bugzilla should treat this attachment as a patch.
            If specified, a content_type doesn't need to be specified as it is forced to text/plain.
            Defaults to false if unspecified.
        :type is_patch: boolean
        :param is_private: True if the attachment should be private, False if public.
            Defaults to false if unspecified.
        :type is_private: boolean

        :raises ValueError: if no bug IDs are specified
        :raises ValueError: if data or filepath arguments aren't specified
        :raises ValueError: if data isn't defined and filepath points to a nonexistent file
        :raises ValueError: if filepath isn't defined and summary or filename isn't specified

        :returns: attachment IDs created
        :rtype: list of attachment IDs
        """
        if not ids:
            raise ValueError('No bug ID(s) specified')

        if data is not None:
            params['data'] = base64.b64encode(data)
        else:
            if filepath is None:
                raise ValueError('Either data or a filepath must be passed as an argument')
            else:
                if not os.path.exists(filepath):
                    raise ValueError('File not found: {}'.format(filepath))
                else:
                    with open(filepath, 'rb') as f:
                        params['data'] = base64.b64encode(f.read())

        if filename is None:
            if filepath is not None:
                filename = os.path.basename(filepath)
            else:
                raise ValueError('A valid filename must be specified')

        if mimetype is None and not is_patch:
            if data is not None:
                mimetype = magic.from_buffer(data, mime=True)
            else:
                mimetype = magic.from_file(filepath, mime=True)

        if summary is None:
            if filepath is not None:
                summary = filename
            else:
                raise ValueError('A valid summary must be specified')

        params = {'ids': ids}
        params['file_name'] = filename
        params['summary'] = summary
        if not is_patch:
            params['content_type'] = mimetype
        params['comment'] = comment
        params['is_patch'] = is_patch

        method = 'Bug.add_attachment'
        req = self.create_request(method, params)
        result = self.send(req)
        return result['attachments']

    def get_fields(self, ids=None, names=None, **kw):
        """Get information about valid bug fields

        :param ids: fields IDs
        :type ids: list of ints
        :param names: field names
        :type names: list of strings

        """
        method = 'Bug.fields'
        params = {}
        if ids is not None:
            params['ids'] = ids
        if names is not None:
            params['names'] = names
        req = self.create_request(method, params)
        data = self.send(req)
        fields = data['fields']
        return fields

    def get_attachment(self, ids):
        """Get attachments from specified attachment IDs

        :raises ValueError: if no attachment IDs are specified
        :rtype: list of :class:`bite.services.bugzilla.BugzillaAttachment` objects
        """
        if not ids:
            raise ValueError('No attachment ID(s) specified')

        method = 'Bug.attachments'
        params = {'attachment_ids': ids}
        req = self.create_request(method, params)
        data = self.send(req)
        attachments = data['attachments']
        for i in ids:
            try:
                yield self.attachment(**attachments[str(i)])
            except KeyError:
                raise ValueError('No such attachment ID: {}'.format(i))

    def get(self, ids, fields=None, get_comments=False,
            get_attachments=False, get_history=False, **kw):
        """Return a bug object given the bug id"""
        # construct list of requests to send
        reqs = []
        reqs.append(GetRequest(self, ids, fields))
        for call in ['attachments', 'comments', 'history']:
            if locals()['get_' + call]:
                req = getattr(sys.modules[__name__], call.capitalize() + 'Request')(self, ids)
                reqs.append(req)
            else:
                reqs.append(NullRequest())
        bugs, attachments, comments, history = self.parallel_send(reqs, size=4)
        return (self.bug(self, bug, comments, attachments, history) for bug in bugs)

    def create(self, product, component, version, summary, description=None, op_sys=None,
               platform=None, priority=None, severity=None, alias=None, assigned_to=None,
               cc=None, target_milestone=None, groups=None, status=None, **kw):
        """Create a new bug given a list of parameters

        :returns: ID of the newly created bug
        :rtype: int
        """
        params = {}
        params['product'] = product
        params['component'] = component
        params['version'] = version
        params['summary'] = summary
        if description is not None:
            params['description'] = description
        if op_sys is not None:
            params['op_sys'] = op_sys
        if platform is not None:
            params['platform'] = platform
        if priority is not None:
            params['priority'] = priority
        if severity is not None:
            params['severity'] = severity
        if alias is not None:
            params['alias'] = alias
        if assigned_to is not None:
            params['assigned_to'] = assigned_to
        if cc is not None:
            params['cc'] = cc
        if target_milestone is not None:
            params['target_milestone'] = target_milestone
        if groups is not None:
            params['groups'] = groups
        if status is not None:
            params['status'] = status

        method = 'Bug.create'
        req = self.create_request(method, params)
        data = self.send(req)
        return data['id']

    def products(self, params):
        """Query bugzilla for product data

        """
        method = 'Product.get'
        req = self.create_request(method, params)
        data = self.send(req)
        return data['products']

    def fields(self, params):
        """Query bugzilla for field data"""
        method = 'Bug.fields'
        req = self.create_request(method, params)
        data = self.send(req)
        return data['fields']

    def users(self, params):
        """Query bugzilla for user data"""
        method = 'User.get'
        req = self.create_request(method, params)
        data = self.send(req)
        return data['users']

    def version(self):
        method = 'Bugzilla.version'
        req = self.create_request(method, params)
        data = self.send(req)
        return data['version']

    def extensions(self):
        method = 'Bugzilla.extensions'
        req = self.create_request(method, params)
        data = self.send(req)
        return data['extensions']

    def query(self, method, params=None):
        """Query bugzilla for various data"""
        req = self.create_request(method, params)
        data = self.send(req)
        return data

setattr(Bugzilla, 'search', lambda self, *args, **kw: SearchRequest(self, *args, **kw))
setattr(Bugzilla, 'comments', lambda self, *args, **kw: CommentsRequest(self, *args, **kw))
setattr(Bugzilla, 'history', lambda self, *args, **kw: HistoryRequest(self, *args, **kw))
setattr(Bugzilla, 'attachments', lambda self, *args, **kw: AttachmentsRequest(self, *args, **kw))
setattr(Bugzilla, 'modify', lambda self, *args, **kw: ModifyRequest(self, *args, **kw))

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
            self.attachments = next(attachments)
        if comments:
            self.comments = next(comments)
        if history:
            self.history = next(history)

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

            values = value
            if isinstance(value, list):
                values = ', '.join(map(str, value))

            lines.append('{:<12}: {}'.format(title, values))

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
            if 'creator' in comment:
                # >= bugzilla-4.0
                creator = comment['creator']
            else:
                creator = comment['author']

        if 'creation_time' in comment:
            # >= bugzilla-4.4
            date = parsetime(comment['creation_time'])
        else:
            date = parsetime(comment['time'])

        if 'count' in comment:
            # >= bugzilla-4.4
            count = comment['count']

        if comment['text'] is None:
            text = None
        else:
            text = comment['text'].strip()

        changes = {}
        if 'attachment_id' in comment:
            changes['attachment_id'] = comment['attachment_id']

        super(BugzillaComment, self).__init__(id=id, creator=creator, date=date,
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
        super(BugzillaEvent, self).__init__(creator=creator, date=date, id=id,
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
        lines.append('-' * 10)
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
    def __init__(self, id, file_name, size=None, content_type=None,
                 data=None, creation_time=None, last_change_time=None, **kw):

        if creation_time is not None:
            creation_time = parsetime(creation_time)
        if last_change_time is not None:
            last_change_time = parsetime(last_change_time)

        map_name = {
            # < bugzilla-4.0
            'attacher': 'creator',
            'description': 'summary',
        }

        for k, v in kw.items():
            try:
                name = map_name[k]
            except KeyError:
                name = k

            setattr(self, name, v)

        super(BugzillaAttachment, self).__init__(
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
        return base64.b64decode(self.data).decode()
