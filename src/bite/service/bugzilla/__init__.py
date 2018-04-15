import base64
import datetime
import os
import re
import string
from urllib.parse import parse_qs

from dateutil.parser import parse as dateparse
from snakeoil.demandload import demandload
from snakeoil.klass import steal_docs

from .. import Service, PagedRequest, NullRequest, Request
from ... import utc
from ...cache import Cache, csv2tuple
from ...exceptions import RequestError, AuthError, BiteError
from ...objects import Item, Change, Comment, Attachment, decompress

demandload('bite:const')


class BugzillaError(RequestError):
    """Bugzilla service specific error."""

    def __init__(self, msg, code=None, text=None):
        msg = 'Bugzilla error: ' + msg
        super().__init__(msg, code, text)


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


class BugzillaComment(Comment):
    """Bugzilla comment object."""

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
    """Bugzilla change object."""

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
    """Generic bugzilla service support."""

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

    @steal_docs(Service)
    def login(self, user, password, restrict_login=False, **kw):
        super().login(user, password, restrict_login=restrict_login)

    @steal_docs(Service)
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
        """Handle bugzilla specific errors.

        Bugzilla web service error codes and their descriptions can be found at:
        https://github.com/bugzilla/bugzilla/blob/5.0/Bugzilla/WebService/Constants.pm#L56
        """
        # (-+)32000: fallback error code for unmapped/unknown errors, negative
        # is fatal and positive is transient
        if code == 32000:
            if 'expired' in msg:
                # assume the auth token has expired
                raise AuthError(msg, expired=True)
        # 102: bug access or query denied due to insufficient permissions
        # 410: login required to perform this request
        elif code in (102, 410):
            raise AuthError(msg=msg)
        raise BugzillaError(msg=msg, code=code)

    def _failed_http_response(self, response):
        if response.status_code in (401, 403):
            data = self.parse_response(response)
            raise AuthError(f"authentication failed: {data.get('message', '')}")
        else:
            super()._failed_http_response(response)


class SearchRequest4_4(PagedRequest):
    """Construct a bugzilla-4.4 compatible search request.

    API docs: https://www.bugzilla.org/docs/4.4/en/html/api/Bugzilla/WebService/Bug.html#search
    """

    def __init__(self, service, **kw):
        params, options = self.parse_params(service=service, **kw)

        if not params:
            raise BiteError('no supported search terms or options specified')

        # only return open bugs by default
        if 'status' not in params:
            params['status'] = service.cache['open_status']

        # set a search limit to make continued requests work as expected
        if 'limit' not in params and service.max_results is not None:
            params['limit'] = service.max_results

        # limit fields by default to decrease requested data size and speed up response
        if 'fields' not in kw:
            fields = ['id', 'assigned_to', 'summary']
        else:
            fields = kw['fields']
            unknown_fields = set(fields).difference(service.item.attributes.keys())
            if unknown_fields:
                raise BiteError(f"unknown fields: {', '.join(unknown_fields)}")
            options.append(f"Fields: {' '.join(fields)}")

        params['include_fields'] = fields

        super().__init__(service=service, params=params, **kw)
        self.fields = fields
        self.options = options

    def parse_params(self, service, params=None, options=None, **kw):
        params = params if params is not None else {}
        options = options if options is not None else []

        for k, v in ((k, v) for (k, v) in kw.items() if v):
            if k in service.item.attributes:
                if k in ['creation_time', 'last_change_time']:
                    params[k] = v.isoformat()
                    options.append(f'{service.item.attributes[k]}: {v} (since {v!r} UTC)')
                elif k in ['assigned_to', 'creator']:
                    params[k] = list(map(service._resuffix, v))
                    options.append(f"{service.item.attributes[k]}: {', '.join(map(str, v))}")
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
                        options.append(f"{service.item.attributes[k]}: {', '.join(status_alias)} ({', '.join(params[k])})")
                    else:
                        options.append(f"{service.item.attributes[k]}: {', '.join(params[k])}")
                else:
                    params[k] = v
                    options.append(f"{service.item.attributes[k]}: {', '.join(map(str, v))}")
            else:
                if k == 'terms':
                    params['summary'] = v
                    options.append(f"Summary: {', '.join(map(str, v))}")
                elif k in ('limit', 'offset'):
                    params[k] = v

        return params, options

    def parse(self, data):
        bugs = data['bugs']
        for bug in bugs:
            yield self.service.item(self.service, **bug)


class SearchRequest5_0(SearchRequest4_4):
    """Construct a bugzilla-5.0 compatible search request.

    Bugzilla 5.0+ allows using any parameters able to be set in the advanced
    search screen of the web UI to be used via the webserver API as well.
    Advanced search field names and the formats bugzilla expects them in can be
    determined by constructing queries using the web UI and looking at the
    resulting URL.

    API docs: https://bugzilla.readthedocs.io/en/5.0/api/core/v1/bug.html#search-bugs
    """

    # map of allowed sorting input values to the names bugzilla expects as parameters
    sorting_map = {
        'alias': 'alias',
        'blocks': 'blocked',
        'comments': 'longdescs.count',
        'component': 'component',
        'created': 'opendate',
        'creator': 'reporter',
        'deadline': 'deadline',
        'depends': 'dependson',
        'id': 'bug_id',
        'keywords': 'keywords',
        'milestone': 'target_milestone',
        'modified': 'changeddate',
        'os': 'op_sys',
        'owner': 'assigned_to',
        'platform': 'rep_platform',
        'priority': 'priority',
        'product': 'product',
        'resolution': 'resolution',
        'severity': 'bug_severity',
        'status': 'bug_status',
        'summary': 'short_desc',
        'version': 'version',
        'last-visited': 'last_visit_ts',
        'votes': 'votes',
        'whiteboard': 'status_whiteboard',
    }

    def parse_params(self, service, params=None, options=None, **kw):
        params = params if params is not None else {}
        options = options if options is not None else []

        for k, v in ((k, v) for (k, v) in dict(kw).items() if v):
            if k in ('cc', 'commenter'):
                v = kw.pop(k)
                for i, val in enumerate(v):
                    params[f'f{i + 1}'] = k
                    params[f'o{i + 1}'] = 'substring'
                    params[f'v{i + 1}'] = val
                options.append(f"{k.capitalize()}: {', '.join(map(str, v))}")
            elif k == 'sort':
                v = kw.pop(k)
                sorting_terms = []
                for x in v:
                    inverse = ''
                    if x[0] == '-':
                        x = x[1:]
                        inverse = ' DESC'
                    try:
                        order_var = self.sorting_map[x]
                    except KeyError:
                        choices = ', '.join(sorted(self.sorting_map.keys()))
                        raise BiteError(
                            f'unable to sort by: {x!r} (available choices: {choices}')
                    sorting_terms.append(f'{order_var}{inverse}')
                params['order'] = ','.join(sorting_terms)
                options.append(f"Sort order: {', '.join(v)}")
            elif k in ('keywords', 'blocks', 'depends_on'):
                v = kw.pop(k)
                params[k] = v
                options.append(f"{service.item.attributes[k]}: {', '.join(map(str, v))}")
            elif k in ('quicksearch', 'votes'):
                v = kw.pop(k)
                params[k] = v
                options.append(f"{k.capitalize()}: {v}")
            elif k == 'advanced_url':
                v = kw.pop(k)
                base, url_params = v.split('?', 1)
                if base != f"{service.base.rstrip('/')}/buglist.cgi":
                    raise BiteError(f'invalid advanced search URL: {v!r}')
                # command line options take precedence over URL parameters
                for k, v in parse_qs(url_params).items():
                    if k not in params:
                        params[k] = v
                options.append('Using advanced search URL')

        return super().parse_params(service, params, options, **kw)


class HistoryRequest(Request):
    """Construct a history request."""

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
            params['new_since'] = created.isoformat()
            options_log.append(f'Created: {created} (since {created!r} UTC)')

        super().__init__(service=service, params=params, **kw)
        self.options = options_log

    def parse(self, data):
        bugs = data['bugs']
        for b in bugs:
            yield [BugzillaEvent(change=x, id=b['id'], alias=b['alias'], count=i)
                   for i, x in enumerate(b['history'], start=1)]


class CommentsRequest(Request):
    """Construct a comments request."""

    def __init__(self, ids=None, comment_ids=None, created=None, fields=None, service=None, **kw):
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
            params['new_since'] = created.isoformat()
            options_log.append(f'Created: {created} (since {created!r} UTC)')
        if fields is not None:
            params['include_fields'] = fields

        self.ids = ids

        super().__init__(service=service, params=params, **kw)
        self.options = options_log

    def parse(self, data):
        bugs = data['bugs']
        for i in self.ids:
            yield [BugzillaComment(comment=comment, id=i, count=j)
                   for j, comment in enumerate(bugs[str(i)]['comments'])]


class AttachmentsRequest(Request):
    """Construct an attachments request."""

    def __init__(self, service, ids=None, attachment_ids=None, fields=None,
                 get_data=False, *args, **kw):
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
    """Construct a modify request."""

    # parameters support add, remove, and possibly set actions
    add_remove = {'groups', 'see_also', 'cc'}
    add_remove_set = {'alias', 'blocks', 'depends', 'keywords'}

    # other params requiring object values
    obj_params = {'comment-{x}' for x in ('body', 'is_private', 'is_markdown')}

    def __init__(self, ids, service, *args, **kw):
        options_log = []
        params = {}

        for k, v in ((k, v) for (k, v) in kw.items() if v):
            if k in self.add_remove:
                try:
                    remove, add = v
                except ValueError:
                    raise ValueError(f"invalid add/remove values for '{k}'")

                if key == 'cc':
                    remove = list(map(service._resuffix, remove))
                    add = list(map(service._resuffix, add))

                values = []
                if remove:
                    params.setdefault(k, {})['remove'] = remove
                    values.extend([f'-{x}' for x in remove])
                if add:
                    params.setdefault(k, {})['add'] = add
                    values.extend([f'+{x}' for x in add])

                options_log.append(
                    '{:<10}: {}'.format(service.item.attributes[k], ', '.join(values)))
            elif k in self.add_remove_set:
                if k == 'alias' and len(ids) > 1:
                    raise ValueError('unable to set aliases on multiple bugs at once')

                # fields supporting add/remove/set actions
                try:
                    remove, set, add = v
                except ValueError:
                    raise ValueError(f"invalid add/remove/set values for '{k}'")

                values = []
                # set overrides add/remove actions
                if set:
                    params.setdefault(k, {})['set'] = set
                    values = set
                else:
                    if remove:
                        params.setdefault(k, {})['remove'] = remove
                        values.extend([f'-{x}' for x in remove])
                    if add:
                        params.setdefault(k, {})['add'] = add
                        values.extend([f'+{x}' for x in add])

                options_log.append(
                    '{:<10}: {}'.format(service.item.attributes[k], ', '.join(values)))
            elif k in self.obj_params:
                key1, key2 = k.split('-')
                params.setdefault(key1, {})[key2] = v
            elif k in service.item.attributes:
                if k == 'assigned_to':
                    v = service._resuffix(v)
                params[k] = v
                options_log.append('{:<10}: {}'.format(service.item.attributes[k], v))
            else:
                raise ValueError(f'unknown parameter: {k!r}')

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
        self.options = options_log

    def parse(self, data):
        return data['bugs']


class AttachRequest(Request):
    """Construct an attach request."""

    def __init__(self, service, ids, data=None, filepath=None, filename=None, mimetype=None,
                 is_patch=False, is_private=False, comment=None, summary=None, **kw):
        """
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
            raise ValueError('No bug ID(s) or aliases specified')

        params = {'ids': ids}

        if data is not None:
            params['data'] = base64.b64encode(data)
        else:
            if filepath is None:
                raise ValueError('Either data or a filepath must be passed as an argument')
            else:
                if not os.path.exists(filepath):
                    raise ValueError(f'File not found: {filepath}')
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

        params['file_name'] = filename
        params['summary'] = summary
        if not is_patch:
            params['content_type'] = mimetype
        params['comment'] = comment
        params['is_patch'] = is_patch

        super().__init__(service=service, params=params, **kw)

    def parse(self, data):
        return data['attachments']


class CreateRequest(Request):
    """Construct a bug creation request."""

    def __init__(self, service, product, component, version, summary, description=None, op_sys=None,
                 platform=None, priority=None, severity=None, alias=None, assigned_to=None,
                 cc=None, target_milestone=None, groups=None, status=None, **kw):
        """
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

        super().__init__(service=service, params=params, **kw)

    def parse(self, data):
        return data['id']


class GetItemRequest(Request):
    """Construct a get request."""

    def __init__(self, ids, service, fields=None, **kw):
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
    """Construct requests to retrieve all known data for given bug IDs."""

    def __init__(self, ids, service, get_comments=False, get_attachments=False,
                 get_history=False, *args, **kw):
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


class LoginRequest(Request):
    """Construct a login request."""

    def __init__(self, user, password, restrict_login=False, **kw):
        params = {
            'login': user,
            'password': password,
            'restrict_login': restrict_login,
        }
        super().__init__(params=params, **kw)

    def parse(self, data):
        return data['token']


class ExtensionsRequest(Request):
    """Construct an extensions request."""

    def parse(self, data):
        return data['extensions']


class VersionRequest(Request):
    """Construct a version request."""

    def parse(self, data):
        return data['version']


class FieldsRequest(Request):
    """Construct a fields request."""

    def __init__(self, ids=None, names=None, **kw):
        """
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
    """Construct a products request."""

    def __init__(self, ids=None, names=None, match=None, **kw):
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
    """Construct a users request."""

    def __init__(self, ids=None, names=None, match=None, **kw):
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
