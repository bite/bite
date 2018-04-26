import base64
import os
from urllib.parse import parse_qs

from snakeoil.demandload import demandload

from .objects import BugzillaEvent, BugzillaComment
from .. import PagedRequest, Request
from ...exceptions import BiteError

demandload('bite:const')


class SearchRequest4_4(PagedRequest):
    """Construct a bugzilla-4.4 compatible search request.

    API docs: https://www.bugzilla.org/docs/4.4/en/html/api/Bugzilla/WebService/Bug.html#search
    """

    _offset_key = 'offset'
    _size_key = 'limit'

    def __init__(self, service, **kw):
        params, options = self.parse_params(service=service, **kw)

        if not params:
            raise BiteError('no supported search terms or options specified')

        # only return open bugs by default
        if 'status' not in params:
            params['status'] = service.cache['open_status']

        # limit fields by default to decrease requested data size and speed up response
        fields = kw.get('fields', None)
        if fields is None:
            fields = ['id', 'assigned_to', 'summary']
        else:
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
        # current advanced search field number
        advanced_num = 1

        for k, v in ((k, v) for (k, v) in dict(kw).items() if v):
            if k in ('cc', 'commenter'):
                v = kw.pop(k)
                for val in v:
                    params[f'f{advanced_num}'] = k
                    params[f'o{advanced_num}'] = 'substring'
                    params[f'v{advanced_num}'] = val
                    advanced_num += 1
                options.append(f"{k.capitalize()}: {', '.join(map(str, v))}")
            elif k == 'comments':
                v = kw.pop(k)
                params[f'f{advanced_num}'] = 'longdescs.count'
                params[f'o{advanced_num}'] = 'greaterthaneq'
                params[f'v{advanced_num}'] = v
                advanced_num += 1
                options.append(f"{k.capitalize()}: {v}")
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
                options.append('Using advanced search URL')
                # command line options take precedence over URL parameters
                for k, v in parse_qs(url_params).items():
                    if k not in params:
                        # Assume lists with one element are supposed to be sent as strings
                        # otherwise the jsonrpc/xmlrpc backends error out.
                        params[k] = v if len(v) > 1 else v[0]
            elif k == 'saved_search':
                saved_search_params = service.saved_searches.get(v, None)
                if saved_search_params is None:
                    raise BiteError(f'no matching saved search: {v!r}')
                options.append(f'Using saved search: {v}')
                for k, v in saved_search_params['params'].items():
                    if k not in params:
                        params[k] = v if len(v) > 1 else v[0]

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
            options_log.insert(0, f'{prefix}-' * (const.COLUMNS - len(prefix)))

        if 'comment' in params:
            prefix = '--- Adding comment '
            options_log.append(f'{prefix}-' * (const.COLUMNS - len(prefix)))
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
        params = {
            'product': product,
            'component': component,
            'version': version,
            'summary': summary,
        }
        options_log = [
            '=' * const.COLUMNS,
            f"Product: {product}",
            f"Component: {component}",
            f"Version: {version}",
            f"Title: {summary}",
        ]

        if op_sys:
            params['op_sys'] = op_sys
            options_log.append(f"OS: {op_sys}")
        if platform:
            params['platform'] = platform
            options_log.append(f"Platform: {platform}")
        if priority:
            params['priority'] = priority
            options_log.append(f"Priority: {priority}")
        if severity:
            params['severity'] = severity
            options_log.append(f"Severity: {severity}")
        if alias:
            params['alias'] = alias
            options_log.append(f"Alias: {alias}")
        if assigned_to:
            params['assigned_to'] = list(map(service._resuffix, assigned_to))
            options_log.append(f"Assigned to: {service._desuffix(assigned_to)}")
        if cc:
            params['cc'] = list(map(service._resuffix, cc))
            options_log.append(f"CC: {', '.join(map(service._desuffix, cc))}")
        if target_milestone:
            params['target_milestone'] = target_milestone
            options_log.append(f"Milestone: {target_milestone}")
        if groups:
            params['groups'] = groups
            options_log.append(f"Groups: {', '.join(groups)}")
        if status:
            params['status'] = status
            options_log.append(f"Status: {status}")

        if description:
            params['description'] = description
            msg = 'Description'
            options_log.append(f'{"-" * 3} {msg} {"-" * (const.COLUMNS - len(msg) - 5)}')
            options_log.append(description)
        options_log.append('=' * const.COLUMNS)

        super().__init__(service=service, params=params, **kw)
        self.options = options_log

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
        bugs = data['bugs']
        for bug in bugs:
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
