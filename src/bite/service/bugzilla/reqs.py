import base64
import os
from urllib.parse import parse_qs

from snakeoil.demandload import demandload

from .objects import BugzillaEvent, BugzillaComment
from .._reqs import OffsetPagedRequest, Request
from ...exceptions import BiteError

demandload('bite:const')


class SearchRequest4_4(OffsetPagedRequest):
    """Construct a bugzilla-4.4 compatible search request.

    API docs: https://www.bugzilla.org/docs/4.4/en/html/api/Bugzilla/WebService/Bug.html#search
    """

    _offset_key = 'offset'
    _size_key = 'limit'

    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        self.param_parser = self.ParamParser(self.service, self.params, self.options)
        self.parse_params(**kw)

        if not self.params:
            raise BiteError('no supported search terms or options specified')

        # only return open bugs by default
        if 'status' not in self.params:
            self.params['status'] = self.service.cache['open_status']

        # limit fields by default to decrease requested data size and speed up response
        fields = kw.get('fields', None)
        if fields is None:
            fields = ['id', 'assigned_to', 'summary']
        else:
            unknown_fields = set(fields).difference(self.service.item.attributes.keys())
            if unknown_fields:
                raise BiteError(f"unknown fields: {', '.join(unknown_fields)}")
            self.options.append(f"Fields: {' '.join(fields)}")

        self.params['include_fields'] = fields
        self.fields = fields

    def parse_params(self, **kw):
        for k, v in ((k, v) for (k, v) in kw.items() if v):
            parse = getattr(self.param_parser, k, None)
            if callable(parse):
                parse(k, v)
            else:
                if k in self.service.item.attributes:
                    self.params[k] = v
                    self.options.append(f"{self.service.item.attributes[k]}: {', '.join(map(str, v))}")

    def parse(self, data):
        bugs = data['bugs']
        for bug in bugs:
            yield self.service.item(self.service, **bug)

    class ParamParser(object):

        def __init__(self, service, params, options):
            self.service = service
            self.params = params
            self.options = options

        def creation_time(self, k, v):
            self.params[k] = v.isoformat()
            self.options.append(f'{self.service.item.attributes[k]}: {v} (since {v!r} UTC)')
        last_change_time = creation_time

        def assigned_to(self, k, v):
            self.params[k] = list(map(self.service._resuffix, v))
            self.options.append(f"{self.service.item.attributes[k]}: {', '.join(map(str, v))}")
        creator = assigned_to

        def status(self, k, v):
            status_alias = []
            status_map = {
                'open': self.service.cache['open_status'],
                'closed': self.service.cache['closed_status'],
                'all': self.service.cache['open_status'] + self.service.cache['closed_status'],
            }
            for status in v:
                if status_map.get(status.lower(), False):
                    status_alias.append(status)
                    self.params.setdefault(k, []).extend(status_map[status.lower()])
                else:
                    self.params.setdefault(k, []).append(status)
            if status_alias:
                self.options.append(f"{self.service.item.attributes[k]}: {', '.join(status_alias)} ({', '.join(self.params[k])})")
            else:
                self.options.append(f"{self.service.item.attributes[k]}: {', '.join(self.params[k])}")

        def terms(self, k, v):
            self.params['summary'] = v
            self.options.append(f"Summary: {', '.join(map(str, v))}")


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

    def parse_params(self, **kw):
        # current advanced search field number
        self.adv_num = 1
        return super().parse_params(**kw)

    class ParamParser(SearchRequest4_4.ParamParser):

        def commenter(self, k, v):
            for val in v:
                self.params[f'f{self.adv_num}'] = k
                self.params[f'o{self.adv_num}'] = 'substring'
                self.params[f'v{self.adv_num}'] = val
                self.adv_num += 1
            self.options.append(f"{k.capitalize()}: {', '.join(map(str, v))}")
        cc = commenter

        def comments(self, k, v):
            self.params[f'f{self.adv_num}'] = 'longdescs.count'
            self.params[f'o{self.adv_num}'] = 'greaterthaneq'
            self.params[f'v{self.adv_num}'] = v
            self.adv_num += 1
            self.options.append(f"{k.capitalize()}: {v}")

        def sort(self, k, v):
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
            self.params['order'] = ','.join(sorting_terms)
            self.options.append(f"Sort order: {', '.join(v)}")

        def keywords(self, k, v):
            self.params[k] = v
            self.options.append(f"{self.service.item.attributes[k]}: {', '.join(map(str, v))}")
        blocks = keywords
        depends_on = keywords

        def quicksearch(self, k, v):
            self.params[k] = v
            self.options.append(f"{k.capitalize()}: {v}")
        votes = quicksearch

        def advanced_url(self, k, v):
            base, url_params = v.split('?', 1)
            if base != f"{self.service.base.rstrip('/')}/buglist.cgi":
                raise BiteError(f'invalid advanced search URL: {v!r}')
            self.options.append('Using advanced search URL')
            # command line options take precedence over URL parameters
            for k, v in parse_qs(url_params).items():
                if k not in self.params:
                    # Assume lists with one element are supposed to be sent as strings
                    # otherwise the jsonrpc/xmlrpc backends error out.
                    self.params[k] = v if len(v) > 1 else v[0]

        def saved_search(self, k, v):
            saved_search_params = self.service.saved_searches.get(v, None)
            if saved_search_params is None:
                raise BiteError(f'no matching saved search: {v!r}')
            self.options.append(f'Using saved search: {v}')
            for k, v in saved_search_params['params'].items():
                if k not in self.params:
                    self.params[k] = v if len(v) > 1 else v[0]


class ChangesRequest(Request):
    """Construct a changes request."""

    def __init__(self, ids, created=None, **kw):
        super().__init__(**kw)
        if not ids:
            raise ValueError('No bug ID(s) specified')

        if ids is not None:
            ids = list(map(str, ids))
            self.params['ids'] = ids
            self.options.append(f"IDs: {', '.join(ids)}")
        if created is not None:
            self.params['new_since'] = created.isoformat()
            self.options.append(f'Created: {created} (since {created!r} UTC)')

    def parse(self, data):
        bugs = data['bugs']
        for b in bugs:
            yield tuple(BugzillaEvent(change=x, id=b['id'], alias=b['alias'], count=i)
                        for i, x in enumerate(b['history'], start=1))


class CommentsRequest(Request):
    """Construct a comments request."""

    def __init__(self, ids=None, comment_ids=None, created=None, fields=None, **kw):
        super().__init__(**kw)
        if ids is None and comment_ids is None:
            raise ValueError(f'No {self.service.item.type} or comment ID(s) specified')

        if ids is not None:
            ids = list(map(str, ids))
            self.params['ids'] = ids
            self.options.append(f"IDs: {', '.join(ids)}")
        if comment_ids is not None:
            comment_ids = list(map(str, comment_ids))
            self.params['comment_ids'] = comment_ids
            self.options.append(f"Comment IDs: {', '.join(comment_ids)}")
        if created is not None:
            self.params['new_since'] = created.isoformat()
            self.options.append(f'Created: {created} (since {created!r} UTC)')
        if fields is not None:
            self.params['include_fields'] = fields

        self.ids = ids

    def parse(self, data):
        bugs = data['bugs']
        for i in self.ids:
            yield tuple(BugzillaComment(comment=comment, id=i, count=j)
                        for j, comment in enumerate(bugs[str(i)]['comments']))


class AttachmentsRequest(Request):
    """Construct an attachments request."""

    def __init__(self, ids=None, attachment_ids=None, fields=None,
                 get_data=False, *args, **kw):
        super().__init__(**kw)
        if ids is None and attachment_ids is None:
            raise ValueError(f'No {self.service.item.type} or attachment ID(s) specified')

        if ids is not None:
            ids = list(map(str, ids))
            self.params['ids'] = ids
            self.options.append(f"IDs: {', '.join(ids)}")
        if attachment_ids is not None:
            attachment_ids = list(map(str, attachment_ids))
            self.params['attachment_ids'] = attachment_ids
            self.options.append(f"Attachment IDs: {', '.join(attachment_ids)}")
        if fields is not None:
            self.params['include_fields'] = fields
        # attachment data doesn't get pulled by default
        if not get_data:
            self.params['exclude_fields'] = ['data']

        self.ids = ids
        self.attachment_ids = attachment_ids

    def parse(self, data):
        if self.ids:
            bugs = data['bugs']
            for i in self.ids:
                yield tuple(self.service.attachment(**attachment) for attachment in bugs[str(i)])

        if self.attachment_ids:
            attachments = data['attachments']
            files = []
            try:
                for i in self.attachment_ids:
                    files.append(self.service.attachment(**attachments[str(i)]))
            except KeyError:
                raise BiteError(f'invalid attachment ID: {i}')
            yield tuple(files)


class ModifyRequest(Request):
    """Construct a modify request."""

    # parameters support add, remove, and possibly set actions
    add_remove = {'groups', 'see_also', 'cc'}
    add_remove_set = {'alias', 'blocks', 'depends', 'keywords'}

    # other params requiring object values
    obj_params = {'comment-{x}' for x in ('body', 'is_private', 'is_markdown')}

    def __init__(self, ids, *args, **kw):
        super().__init__(*args, **kw)
        for k, v in ((k, v) for (k, v) in kw.items() if v):
            if k in self.add_remove:
                try:
                    remove, add = v
                except ValueError:
                    raise ValueError(f"invalid add/remove values for '{k}'")

                if key == 'cc':
                    remove = list(map(self.service._resuffix, remove))
                    add = list(map(self.service._resuffix, add))

                values = []
                if remove:
                    self.params.setdefault(k, {})['remove'] = remove
                    values.extend([f'-{x}' for x in remove])
                if add:
                    self.params.setdefault(k, {})['add'] = add
                    values.extend([f'+{x}' for x in add])

                self.options.append(
                    '{:<10}: {}'.format(self.service.item.attributes[k], ', '.join(values)))
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
                    self.params.setdefault(k, {})['set'] = set
                    values = set
                else:
                    if remove:
                        self.params.setdefault(k, {})['remove'] = remove
                        values.extend([f'-{x}' for x in remove])
                    if add:
                        self.params.setdefault(k, {})['add'] = add
                        values.extend([f'+{x}' for x in add])

                self.options.append(
                    '{:<10}: {}'.format(self.service.item.attributes[k], ', '.join(values)))
            elif k in self.obj_params:
                key1, key2 = k.split('-')
                self.params.setdefault(key1, {})[key2] = v
            elif k in self.service.item.attributes:
                if k == 'assigned_to':
                    v = self.service._resuffix(v)
                self.params[k] = v
                self.options.append('{:<10}: {}'.format(self.service.item.attributes[k], v))
            else:
                raise ValueError(f'unknown parameter: {k!r}')

        if not self.params:
            raise ValueError('No changes specified')

        if self.options:
            prefix = '--- Modifying fields '
            self.options.insert(0, f'{prefix}-' * (const.COLUMNS - len(prefix)))

        if 'comment' in self.params:
            prefix = '--- Adding comment '
            self.options.append(f'{prefix}-' * (const.COLUMNS - len(prefix)))
            self.options.append(self.params['comment']['body'])

        self.options.append('-' * const.COLUMNS)

        if not ids:
            raise ValueError('No bug ID(s) specified')
        self.params['ids'] = ids

    def parse(self, data):
        return data['bugs']


class AttachRequest(Request):
    """Construct an attach request."""

    def __init__(self, ids, data=None, filepath=None, filename=None, mimetype=None,
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
        super().__init__(**kw)
        if not ids:
            raise ValueError('No bug ID(s) or aliases specified')

        self.params['ids'] = ids

        if data is not None:
            self.params['data'] = base64.b64encode(data)
        else:
            if filepath is None:
                raise ValueError('Either data or a filepath must be passed as an argument')
            else:
                if not os.path.exists(filepath):
                    raise ValueError(f'File not found: {filepath}')
                else:
                    with open(filepath, 'rb') as f:
                        self.params['data'] = base64.b64encode(f.read())

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

        self.params['file_name'] = filename
        self.params['summary'] = summary
        if not is_patch:
            self.params['content_type'] = mimetype
        self.params['comment'] = comment
        self.params['is_patch'] = is_patch

    def parse(self, data):
        return data['attachments']


class CreateRequest(Request):
    """Construct a bug creation request."""

    def __init__(self, product, component, version, summary, description=None, op_sys=None,
                 platform=None, priority=None, severity=None, alias=None, assigned_to=None,
                 cc=None, target_milestone=None, groups=None, status=None, **kw):
        """
        :returns: ID of the newly created bug
        :rtype: int
        """
        super().__init__(**kw)
        self.params.update({
            'product': product,
            'component': component,
            'version': version,
            'summary': summary,
        })
        self.options.extend([
            '=' * const.COLUMNS,
            f"Product: {product}",
            f"Component: {component}",
            f"Version: {version}",
            f"Title: {summary}",
        ])

        if op_sys:
            self.params['op_sys'] = op_sys
            self.options.append(f"OS: {op_sys}")
        if platform:
            self.params['platform'] = platform
            self.options.append(f"Platform: {platform}")
        if priority:
            self.params['priority'] = priority
            self.options.append(f"Priority: {priority}")
        if severity:
            self.params['severity'] = severity
            self.options.append(f"Severity: {severity}")
        if alias:
            self.params['alias'] = alias
            self.options.append(f"Alias: {alias}")
        if assigned_to:
            self.params['assigned_to'] = list(map(service._resuffix, assigned_to))
            self.options.append(f"Assigned to: {service._desuffix(assigned_to)}")
        if cc:
            self.params['cc'] = list(map(service._resuffix, cc))
            self.options.append(f"CC: {', '.join(map(service._desuffix, cc))}")
        if target_milestone:
            self.params['target_milestone'] = target_milestone
            self.options.append(f"Milestone: {target_milestone}")
        if groups:
            self.params['groups'] = groups
            self.options.append(f"Groups: {', '.join(groups)}")
        if status:
            self.params['status'] = status
            self.options.append(f"Status: {status}")

        if description:
            self.params['description'] = description
            msg = 'Description'
            self.options.append(f'{"-" * 3} {msg} {"-" * (const.COLUMNS - len(msg) - 5)}')
            self.options.append(description)
        self.options.append('=' * const.COLUMNS)

    def parse(self, data):
        return data['id']


class GetItemRequest(Request):
    """Construct a get request."""

    def __init__(self, ids, fields=None, **kw):
        super().__init__(**kw)
        if not ids:
            raise ValueError('No bug ID(s) specified')

        self.params['ids'] = ids
        if fields is not None:
            self.params['include_fields'] = fields

    def parse(self, data):
        bugs = data['bugs']
        for bug in bugs:
            yield self.service.item(self.service, **bug)


class LoginRequest(Request):
    """Construct a login request."""

    def __init__(self, user, password, restrict_login=False, **kw):
        super().__init__(**kw)
        self.params = {
            'login': user,
            'password': password,
            'restrict_login': restrict_login,
        }

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
        super().__init__(**kw)

        if ids is None and names is None:
            self.options.append('all non-obsolete fields')

        if ids is not None:
            ids = list(map(str, ids))
            self.params['ids'] = ids
            self.options.append(f"IDs: {', '.join(ids)}")
        if names is not None:
            self.params['names'] = names
            self.options.append(f"Field names: {', '.join(names)}")

    def parse(self, data):
        return data['fields']


class ProductsRequest(Request):
    """Construct a products request."""

    def __init__(self, ids=None, names=None, match=None, **kw):
        super().__init__(**kw)

        if ids is None and names is None:
            # TODO: not supported in bugzilla-4.4 -- must call get_accessible_products to get IDs
            self.params['type'] = ['accessible']
            self.options.append('all user-accessible products')

        if ids is not None:
            ids = list(map(str, ids))
            self.params['ids'] = ids
            self.options.append(f"IDs: {', '.join(ids)}")
        if names is not None:
            self.params['names'] = names
            self.options.append(f"Product names: {', '.join(names)}")

    def parse(self, data):
        return data['products']


class UsersRequest(Request):
    """Construct a users request."""

    def __init__(self, ids=None, names=None, match=None, **kw):
        super().__init__(**kw)
        if not any((ids, names, match)):
            raise ValueError('No user ID(s), name(s), or match(es) specified')

        if ids is not None:
            ids = list(map(str, ids))
            self.params['ids'] = ids
            self.options.append(f"IDs: {', '.join(ids)}")
        if names is not None:
            self.params['names'] = names
            self.options.append(f"Login names: {', '.join(names)}")
        if match is not None:
            self.params['match'] = match
            self.options.append(f"Match patterns: {', '.join(match)}")

    def parse(self, data):
        return data['users']
