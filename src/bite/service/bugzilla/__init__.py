import base64
import datetime
from itertools import chain
import re
import string

from dateutil.parser import parse as dateparse
from snakeoil import klass

from .. import Service, ContinuedRequest, NullRequest, Request
from ... import const, utc
from ...cache import Cache, csv2tuple
from ...exceptions import RequestError, AuthError, BiteError
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

    @klass.jit_attr
    def events(self):
        comments = self.comments if self.comments is not None else ()
        history = self.history if self.history is not None else ()
        return sorted(chain(comments, history), key=lambda event: event.date)

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

            lines.append(f'{title:<12}: {value}')

        custom_fields = ((k, v) for (k, v) in vars(self).items()
                         if re.match(r'^cf_\w+$', k))
        for k, v in custom_fields:
            if isinstance(v, list):
                value = ', '.join(v)
            else:
                value = v
            title = string.capwords(k[3:], '_')
            title = title.replace('_', ' ')
            lines.append(f'{title:<12}: {value}')

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
            if comment['creator'].get('real_name', None):
                creator = f"{comment['creator']['real_name']} ({comment['creator']['name']}"
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

        lines = [f'Change #{self.count} by {self.creator}, {self.date}']
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
                lines.append(f"{field}: {change['attachment_id']}")
            else:
                if change['removed'] and change['added']:
                    changes = f"{change['removed']} -> {change['added']}"
                elif change['removed']:
                    changes = ', '.join(['-' + c for c in change['removed'].split(', ')])
                elif change['added']:
                    changes = ', '.join(['+' + c for c in change['added'].split(', ')])
                lines.append(f'{field}: {changes}')

        return '\n'.join(lines)


class BugzillaAttachment(Attachment):

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
            if self.size < 1024 * 1024:
                size = f'{round(self.size / 1024.0, 2)}K'
            else:
                size = f'{round(self.size / 1024 * 1024.0, 2)}M'

            return f'Attachment: [{self.id}] [{self.summary}] ({size}, {self.mimetype})'
        else:
            return f'Attachment: [{self.id}] [{self.summary}]'

    @decompress
    def read(self):
        return base64.b64decode(self.data)


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

    _cache_cls = BugzillaCache

    item = BugzillaBug
    item_endpoint = '/show_bug.cgi?id='
    attachment = BugzillaAttachment
    attachment_endpoint = '/attachment.cgi?id='

    def __init__(self, max_results=None, *args, **kw):
        # most bugzilla instances default to 10k results per req
        if max_results is None:
            max_results = 10000
        super().__init__(*args, max_results=max_results, **kw)

    @property
    def cache_updates(self):
        """Pull latest data from service for cache update."""
        config_updates = {}
        reqs = []

        # get open/closed status values
        reqs.append(self.FieldsRequest(names=['bug_status']))
        # get available products
        reqs.append(self.ProductsRequest())
        # get server bugzilla version
        reqs.append(self.VersionRequest())

        statuses, products, version = self.send(reqs)

        open_status = []
        closed_status = []
        for status in statuses[0].get('values', []):
            if status.get('name', None) is not None:
                if status.get('is_open', False):
                    open_status.append(status['name'])
                else:
                    closed_status.append(status['name'])
        products = [d['name'] for d in sorted(products, key=lambda x: x['id']) if d['is_active']]
        config_updates['open_status'] = tuple(sorted(open_status))
        config_updates['closed_status'] = tuple(sorted(closed_status))
        config_updates['products'] = tuple(products)
        config_updates['version'] = version

        return config_updates

    def login(self, user, password, restrict_login=False, **kw):
        """Authenticate a session."""
        super().login(user, password, restrict_login=restrict_login)

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

    @staticmethod
    def handle_error(code, msg):
        if code == 32000:
            if 'expired' in msg:
                # assume the auth token has expired
                raise AuthError(msg, expired=True)
        elif code == 102:
            raise AuthError(msg=msg)
        raise BugzillaError(msg=msg, code=code)

    def _failed_http_response(self, response):
        if response.status_code in (401, 403):
            data = self.parse_response(response)
            raise AuthError(f"authentication failed: {data.get('message', '')}")
        else:
            super()._failed_http_response(response)


class SearchRequest(ContinuedRequest):

    def __init__(self, service, **kw):
        """Construct a search request."""
        params = {}
        options_log = []
        for k, v in ((k, v) for (k, v) in kw.items() if v):
            if k in service.item.attributes:
                if k in ['creation_time', 'last_change_time']:
                    params[k] = v.format
                    options_log.append(f'{service.item.attributes[k]}: {v.token} (since {v} UTC)')
                elif k in ['assigned_to', 'creator']:
                    params[k] = list(map(service._resuffix, v))
                    options_log.append(f"{service.item.attributes[k]}: {', '.join(map(str, v))}")
                elif k == 'status':
                    status_alias = []
                    status_map = {
                        'open': service.cache['open_status'],
                        'closed': service.cache['closed_status'],
                        'all': service.cache['open_status'] + service.cache['closed_status'],
                    }
                    for status in v:
                        if status_map.get(status.lower(), False):
                            status_alias.append(status)
                            params.setdefault(k, []).extend(status_map[status.lower()])
                        else:
                            params.setdefault(k, []).append(status)
                    if status_alias:
                        options_log.append(f"{service.item.attributes[k]}: {', '.join(status_alias)} ({', '.join(params[k])})")
                    else:
                        options_log.append(f"{service.item.attributes[k]}: {', '.join(params[k])}")
                else:
                    params[k] = v
                    options_log.append(f"{service.item.attributes[k]}: {', '.join(map(str, v))}")
            else:
                if k == 'terms':
                    params['summary'] = v
                    options_log.append(f"Summary: {', '.join(map(str, v))}")
                elif k == 'commenter':
                    # XXX: probably fragile since it uses custom search URL params
                    # only works with >=bugzilla-5, previous versions return invalid parameter errors
                    for i, val in enumerate(v):
                        i = str(i + 1)
                        params['f' + i] = 'commenter'
                        params['o' + i] = 'substring'
                        params['v' + i] = val
                    options_log.append(f"Commenter: {', '.join(map(str, v))}")
                elif k in ['limit', 'offset', 'votes']:
                    params[k] = v

        if not params:
            raise BiteError('no supported search terms or options specified')

        # only return open bugs by default
        if 'status' not in params:
            params['status'] = service.cache['open_status']

        # set a search limit to make continued requests work as expected
        if 'limit' not in params and service.max_results is not None:
            params['limit'] = service.max_results

        if 'fields' not in kw:
            fields = ['id', 'assigned_to', 'summary']
        else:
            fields = kw['fields']
            unknown_fields = set(fields).difference(service.item.attributes.keys())
            if unknown_fields:
                raise BiteError(f"unknown fields: {', '.join(unknown_fields)}")
            options_log.append(f"Fields: {' '.join(fields)}")

        params['include_fields'] = fields

        super().__init__(service=service, params=params, **kw)
        self.params = params
        self.fields = fields
        self.options = options_log

    def parse(self, data):
        bugs = data['bugs']
        for bug in bugs:
            yield self.service.item(self.service, **bug)


class HistoryRequest(Request):
    def __init__(self, ids, created=None, service=None, **kw):
        if not ids:
            raise ValueError('No bug ID(s) specified')

        params = {}
        options_log = []

        if ids is not None:
            ids = list(map(str, ids))
            params['ids'] = ids
            options_log.append(f"IDs: {', '.join(ids)}")
        if created is not None:
            params['new_since'] = created.format
            options_log.append(f'Created: {created.token} (since {created} UTC)')

        super().__init__(service=service, params=params, **kw)
        self.params = params
        self.options = options_log

    def parse(self, data):
        bugs = data['bugs']
        for b in bugs:
            yield [BugzillaEvent(change=x, id=b['id'], alias=b['alias'], count=i)
                   for i, x in enumerate(b['history'], start=1)]


class CommentsRequest(Request):
    def __init__(self, ids=None, comment_ids=None, created=None, fields=None, service=None, **kw):
        """Construct a comments request."""
        if ids is None and comment_ids is None:
            raise ValueError(f'No {service.item.type} or comment ID(s) specified')

        params = {}
        options_log = []

        if ids is not None:
            ids = list(map(str, ids))
            params['ids'] = ids
            options_log.append(f"IDs: {', '.join(ids)}")
        if comment_ids is not None:
            comment_ids = list(map(str, comment_ids))
            params['comment_ids'] = comment_ids
            options_log.append(f"Comment IDs: {', '.join(comment_ids)}")
        if created is not None:
            params['new_since'] = created.format
            options_log.append(f'Created: {created.token} (since {created} UTC)')
        if fields is not None:
            params['include_fields'] = fields

        self.ids = ids

        super().__init__(service=service, params=params, **kw)
        self.params = params
        self.options = options_log

    def parse(self, data):
        bugs = data['bugs']
        for i in self.ids:
            yield [BugzillaComment(comment=comment, id=i, count=j)
                   for j, comment in enumerate(bugs[str(i)]['comments'])]


class AttachmentsRequest(Request):
    def __init__(self, service, ids=None, attachment_ids=None, fields=None,
                 get_data=False, *args, **kw):
        """Construct an attachments request."""
        if ids is None and attachment_ids is None:
            raise ValueError(f'No {service.item.type} or attachment ID(s) specified')

        params = {}
        options_log = []

        if ids is not None:
            ids = list(map(str, ids))
            params['ids'] = ids
            options_log.append(f"IDs: {', '.join(ids)}")
        if attachment_ids is not None:
            attachment_ids = list(map(str, attachment_ids))
            params['attachment_ids'] = attachment_ids
            options_log.append(f"Attachment IDs: {', '.join(attachment_ids)}")
        if fields is not None:
            params['include_fields'] = fields
        # attachment data doesn't get pulled by default
        if not get_data:
            params['exclude_fields'] = ['data']

        super().__init__(service=service, params=params, **kw)
        self.options = options_log
        self.ids = ids
        self.attachment_ids = attachment_ids

    def parse(self, data):
        if self.ids:
            bugs = data['bugs']
            for i in self.ids:
                yield [self.service.attachment(**attachment) for attachment in bugs[str(i)]]

        if self.attachment_ids:
            attachments = data['attachments']
            files = []
            try:
                for i in self.attachment_ids:
                    files.append(self.service.attachment(**attachments[str(i)]))
            except KeyError:
                raise BiteError(f'invalid attachment ID: {i}')
            yield files


class ModifyRequest(Request):
    def __init__(self, ids, service, *args, **kw):
        """Construct a modify request."""
        options_log = []
        params = {}
        for k, v in ((k, v) for (k, v) in kw.items() if v):
            if k in service.item.attributes:
                if k == 'assigned_to':
                    v = service._resuffix(v)
                params[k] = v
                options_log.append('{:<10}: {}'.format(service.item.attributes[k], v))
            elif '-' in k:
                keys = k.split('-')
                if len(keys) != 2:
                    raise RuntimeError('Argument parsing error')
                else:
                    if keys[0] == 'cc':
                        v = list(map(service._resuffix, v))
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
                            options_log.append('{:<10}: {}'.format(service.item.attributes[keys[0]], v))
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
                options_log.append('{:<10}: {}'.format(service.item.attributes[key], ', '.join(value)))
            except KeyError:
                options_log.append('{:<10}: {}'.format(key.capitalize(), ', '.join(value)))

        # remove old entries
        options_log = [x for i, x in enumerate(options_log) if i not in old_indices]

        if not params:
            raise ValueError('No changes specified')

        if options_log:
            prefix = '--- Modifying fields '
            options_log.insert(0, prefix + '-' * (const.COLUMNS - len(prefix)))

        if 'comment' in params:
            prefix = '--- Adding comment '
            options_log.append(prefix + '-' * (const.COLUMNS - len(prefix)))
            options_log.append(params['comment']['body'])

        options_log.append('-' * const.COLUMNS)

        if not ids:
            raise ValueError('No bug ID(s) specified')
        params['ids'] = ids

        super().__init__(service=service, params=params, **kw)
        self.params = params
        self.options = options_log

    def parse(self, data):
        return data['bugs']


class GetItemRequest(Request):
    def __init__(self, ids, service, fields=None, **kw):
        """Construct a get request."""
        if not ids:
            raise ValueError('No bug ID(s) specified')

        params = {}
        params['ids'] = ids
        if fields is not None:
            params['include_fields'] = fields

        super().__init__(service=service, params=params, **kw)

    def parse(self, data):
        return data['bugs']


class GetRequest(Request):
    def __init__(self, ids, service, get_comments=False, get_attachments=False,
                 get_history=False, *args, **kw):
        """Construct requests to retrieve all known data for given bug IDs."""
        if not ids:
            raise ValueError('No bug ID(s) specified')

        reqs = [service.GetItemRequest(ids=ids)]
        for call in ('attachments', 'comments', 'history'):
            if locals()['get_' + call]:
                reqs.append(getattr(service, call.capitalize() + 'Request')(ids=ids))
            else:
                reqs.append(NullRequest(generator=True))

        super().__init__(service=service, reqs=reqs)

    def parse(self, data):
        bugs, attachments, comments, history = data
        for bug in bugs:
            bug['comments'] = next(comments)
            bug['attachments'] = next(attachments)
            bug['history'] = next(history)
            yield self.service.item(self.service, **bug)


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
            options_log.append(f"IDs: {', '.join(ids)}")
        if names is not None:
            params['names'] = names
            options_log.append(f"Field names: {', '.join(names)}")

        super().__init__(params=params, **kw)
        self.options = options_log

    def parse(self, data):
        return data['fields']


class ProductsRequest(Request):

    def __init__(self, ids=None, names=None, match=None, **kw):
        """Query bugzilla for product data."""
        params = {}
        options_log = []

        if ids is None and names is None:
            # TODO: not supported in bugzilla-4.4 -- must call get_accessible_products to get IDs
            params['type'] = ['accessible']
            options_log.append('all user-accessible products')

        if ids is not None:
            ids = list(map(str, ids))
            params['ids'] = ids
            options_log.append(f"IDs: {', '.join(ids)}")
        if names is not None:
            params['names'] = names
            options_log.append(f"Product names: {', '.join(names)}")

        super().__init__(params=params, **kw)
        self.options = options_log

    def parse(self, data):
        return data['products']


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
            options_log.append(f"IDs: {', '.join(ids)}")
        if names is not None:
            params['names'] = names
            options_log.append(f"Login names: {', '.join(names)}")
        if match is not None:
            params['match'] = match
            options_log.append(f"Match patterns: {', '.join(match)}")

        super().__init__(params=params, **kw)
        self.options = options_log

    def parse(self, data):
        return data['users']
