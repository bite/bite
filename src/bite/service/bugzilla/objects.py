import base64
import datetime
import re
import string

from dateutil.parser import parse as dateparse
from snakeoil.demandload import demandload
from snakeoil.osutils import sizeof_fmt

from ... import utc
from ...objects import Item, Change, Comment, Attachment, decompress

demandload('bite:const')


def parsetime(time):
    if not isinstance(time, datetime.datetime):
        return dateparse(str(time))
    else:
        return time.replace(tzinfo=utc.utc)


class BugzillaBug(Item):
    """Bugzilla bug object."""

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
        'title': 'summary',
        'changes': 'history',
    }

    _print_fields = (
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
    )

    type = 'bug'

    def __init__(self, service, **kw):
        self.service = service

        for k, v in kw.items():
            if not v or v == '---':
                # skip empty lists and blank fields
                continue
            elif v == 'flags':
                self.flags = [flag['name'] for flag in kw['flags']]
            elif k in ['creation_time', 'last_change_time']:
                setattr(self, k, parsetime(v))
            else:
                if isinstance(v, str) and re.match(r'^\d\d\d\d-\d\d-\d\dT\d\d:\d\d:\d\dZ$', v):
                    setattr(self, k, parsetime(v))
                else:
                    setattr(self, k, v)

    def _custom_str_fields(self):
        custom_fields = ((k, v) for (k, v) in vars(self).items()
                         if re.match(r'^cf_\w+$', k))
        for k, v in custom_fields:
            title = string.capwords(k[3:], '_')
            title = title.replace('_', ' ')

            value = v
            if isinstance(v, str):
                value = v.splitlines()
            if len(value) > 1:
                # output indented list for multiline custom fields
                prefix = '\n  '
            else:
                prefix = ''
            v = prefix + f'{prefix}'.join(value)
            yield f'{title:<12}: {v}'

    def __getattribute__(self, name):
        value = object.__getattribute__(self, name)
        if name == 'cc' and isinstance(value, list):
            return list(map(self.service._desuffix, value))
        elif isinstance(value, str):
            return self.service._desuffix(value)
        else:
            return value


class BugzillaComment(Comment):
    """Bugzilla comment object."""

    def __init__(self, comment, id, count, rest=False, **kw):
        self.comment_id = comment['id']

        if rest:
            if comment['creator'].get('real_name'):
                creator = f"{comment['creator']['real_name']} ({comment['creator']['name']}"
            else:
                creator = comment['creator']['name']
        else:
            creator = comment['creator']

        created = parsetime(comment['creation_time'])
        count = comment['count']

        if comment['text'] is None:
            text = None
        else:
            text = comment['text'].strip()

        changes = {}
        if 'attachment_id' in comment:
            changes['attachment_id'] = comment['attachment_id']

        super().__init__(
            id=id, creator=creator, created=created,
            count=count, changes=changes, text=text)


class BugzillaEvent(Change):
    """Bugzilla change object."""

    change_aliases = {
        'attachment-description': 'attachments.description',
        'attachment-filename': 'attachments.filename',
        'attachment-mimetype': 'attachments.mimetype',
        'attachment-obsolete': 'attachments.isobsolete',
        'attachment-patch': 'attachments.ispatch',
        'blocks': 'blocked',
        'cc-accessible': 'cclist_accessible',
        'confirmed': 'everconfirmed',
        'depends': 'dependson',
        'flagname': 'flagtypes.name',
        'group': 'bug_group',
        'platform': 'rep_platform',
        'reporter-accessible': 'reporter_accessible',
        'severity': 'bug_severity',
        'title': 'short_desc',
        'url': 'bug_file_loc',
        'whiteboard': 'status_whiteboard',
        'milestone': 'target_milestone',
    }

    _print_fields = {
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
    _print_fields.update(BugzillaBug.attributes)

    _change_map = {
        '---': None,
        '': None,
    }

    def __init__(self, change, id, alias=None, count=None, rest=False, **kw):
        self.alias = alias
        if rest:
            creator = change['changer']['name']
            created = parsetime(change['change_time'])
        else:
            creator = change['who']
            created = parsetime(change['when'])
        changes = {}
        for c in change['changes']:
            removed, added = c['removed'], c['added']
            removed = self._change_map.get(removed, removed)
            added = self._change_map.get(added, added)
            changes[c['field_name']] = (removed, added)
        super().__init__(
            creator=creator, created=created, id=id,
            changes=changes, count=count)

    def __str__(self):
        lines = [f'Change #{self.count} by {self.creator}, {self.created}']
        lines.append('-' * const.COLUMNS)
        for k, v in self.changes.items():
            removed, added = v
            try:
                field = self._print_fields[k]
            except KeyError:
                field = k
                if re.match(r'^cf_\w+$', field):
                    field = string.capwords(field[3:], '_')
                    field = field.replace('_', ' ')

            if k == 'attachments.isobsolete':
                lines.append(f"{field}: {change['attachment_id']}")
            else:
                if removed and added:
                    changes = f"{removed} -> {added}"
                elif removed:
                    changes = ', '.join([f'-{c}' for c in removed.split(', ')])
                elif added:
                    changes = ', '.join([f'+{c}' for c in added.split(', ')])
                lines.append(f'{field}: {changes}')

        return '\n'.join(lines)


class BugzillaAttachment(Attachment):
    """Bugzilla attachment object."""

    def __init__(self, id, file_name, size=None, content_type=None,
                 data=None, creator=None, creation_time=None, last_change_time=None, **kw):

        if creation_time is not None:
            creation_time = parsetime(creation_time)
        if last_change_time is not None:
            last_change_time = parsetime(last_change_time)

        for k, v in kw.items():
            setattr(self, k, v)

        super().__init__(
            id=id, filename=file_name, size=size, mimetype=content_type,
            data=data, creator=creator, created=creation_time, modified=last_change_time)

    def __str__(self):
        if self.size is not None:
            return f'Attachment: [{self.id}] [{self.summary}] ({sizeof_fmt(self.size)}, {self.mimetype})'
        else:
            return f'Attachment: [{self.id}] [{self.summary}]'

    @decompress
    def read(self):
        return base64.b64decode(self.data)
