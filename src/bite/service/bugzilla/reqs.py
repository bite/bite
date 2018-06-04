import base64
import os
from urllib.parse import parse_qs

from snakeoil.demandload import demandload
from snakeoil.klass import aliased, alias

from . import Bugzilla
from .objects import BugzillaEvent, BugzillaComment
from .._reqs import (
    OffsetPagedRequest, Request, ParseRequest, req_cmd,
    BaseGetRequest, BaseCommentsRequest, BaseChangesRequest,
)
from ...exceptions import BiteError

demandload('bite:const')


@req_cmd(Bugzilla, cmd='get')
class _GetRequest(BaseGetRequest):
    """Construct a get request."""


class SearchRequest4_4(ParseRequest, OffsetPagedRequest):
    """Construct a bugzilla-4.4 compatible search request.

    API docs: https://www.bugzilla.org/docs/4.4/en/html/api/Bugzilla/WebService/Bug.html#search
    """

    # paging request keys
    _offset_key = 'offset'
    _size_key = 'limit'

    # map from standardized kwargs name to expected service parameter name
    _params_map = {
        'created': 'creation_time',
        'modified': 'last_change_time',
    }

    def parse(self, data):
        bugs = data['bugs']
        for bug in bugs:
            yield self.service.item(self.service, **bug)

    @aliased
    class ParamParser(ParseRequest.ParamParser):

        def _finalize(self):
            if not self.params:
                raise BiteError('no supported search terms or options specified')

            # only return open bugs by default
            if 'status' not in self.params:
                self.params['status'] = self.service.cache['open_status']

            # limit fields by default to decrease requested data size and speed up response
            if 'include_fields' not in self.params:
                self.params['include_fields'] = ['id', 'assigned_to', 'summary']

        def _default_parser(self, k, v):
            if k in self.service.item.attributes and v:
                self.params[k] = v
                values = ', '.join(map(str, v)) if isinstance(v, (list, tuple)) else v
                self.options.append(f'{self.service.item.attributes[k]}: {values}')
                return k

        def fields(self, k, v):
            available = self.service.item.attributes.keys()
            unknown_fields = set(v).difference(available)
            if unknown_fields:
                raise BiteError(f"unknown fields: {', '.join(map(repr, unknown_fields))} "
                                f"(available: {', '.join(sorted(available))}")
            self.params['include_fields'] = v
            self.options.append(f"Fields: {' '.join(v)}")

        @alias('modified')
        def created(self, k, v):
            self.params[k] = v.isoformat()
            self.options.append(f'{k.capitalize()}: {v} (since {v!r} UTC)')

        @alias('creator', 'qa_contact')
        def assigned_to(self, k, v):
            self.params[k] = list(map(self.service._resuffix, v))
            self.options.append(f"{self.service.item.attributes[k]}: {', '.join(map(str, v))}")

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
                params_str = f"{', '.join(status_alias)} ({', '.join(self.params[k])})"
            else:
                params_str = ', '.join(self.params[k])
            self.options.append(f"Status: {params_str}")

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

    @aliased
    class ParamParser(SearchRequest4_4.ParamParser):

        # map of allowed sorting input values to the names bugzilla expects as parameters
        _sorting_map = {
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

        def __init__(self, **kw):
            super().__init__(**kw)
            self.adv_num = 1

        def _finalize(self):
            # default to sorting ascending by ID
            sort = self.params.pop('sort', 'id')
            super()._finalize()
            self.params['order'] = sort

        @alias('cc')
        def commenter(self, k, v):
            for val in v:
                self.params[f'f{self.adv_num}'] = k
                self.params[f'o{self.adv_num}'] = 'substring'
                self.params[f'v{self.adv_num}'] = val
                self.adv_num += 1
            self.options.append(f"{k.capitalize()}: {', '.join(map(str, v))}")

        @alias('modified')
        def created(self, k, v):
            field = 'creation_ts' if k == 'created' else 'delta_ts'
            if v.start is not None:
                self.params[f'f{self.adv_num}'] = field
                self.params[f'o{self.adv_num}'] = 'greaterthan'
                self.params[f'v{self.adv_num}'] = v.start.isoformat()
                self.adv_num += 1
            if v.end is not None:
                self.params[f'f{self.adv_num}'] = field
                self.params[f'o{self.adv_num}'] = 'lessthan'
                self.params[f'v{self.adv_num}'] = v.end.isoformat()
                self.adv_num += 1
            self.options.append(f'{k.capitalize()}: {v} ({v!r} UTC)')

        def comments(self, k, v):
            self.params[f'f{self.adv_num}'] = 'longdescs.count'
            self.params[f'o{self.adv_num}'] = 'greaterthaneq'
            self.params[f'v{self.adv_num}'] = v
            self.adv_num += 1
            self.options.append(f"{k.capitalize()}: {v}")

        def attachments(self, k, v):
            val = 'isnotempty' if v else 'isempty'
            display_val = 'yes' if v else 'no'
            self.params[f'f{self.adv_num}'] = 'attach_data.thedata'
            self.params[f'o{self.adv_num}'] = val
            self.adv_num += 1
            self.options.append(f"{k.capitalize()}: {display_val}")

        def changed(self, k, v):
            field, time = v
            if time.start is not None:
                self.params[f'f{self.adv_num}'] = field
                self.params[f'o{self.adv_num}'] = 'changedafter'
                self.params[f'v{self.adv_num}'] = time.start.isoformat()
                self.adv_num += 1
            if time.end is not None:
                self.params[f'f{self.adv_num}'] = field
                self.params[f'o{self.adv_num}'] = 'changedbefore'
                self.params[f'v{self.adv_num}'] = time.end.isoformat()
                self.adv_num += 1
            self.options.append(
                f"{field.capitalize()} changed: {time} ({time!r} UTC)")

        @alias('changed_to')
        def changed_from(self, k, v):
            field, value = v
            self.params[f'f{self.adv_num}'] = field
            self.params[f'o{self.adv_num}'] = k.replace('_', '')
            self.params[f'v{self.adv_num}'] = value
            self.adv_num += 1
            self.options.append(
                f"{field.capitalize()} changed {k.split('_')[1]}: {value!r}")

        def changed_by(self, k, v):
            field, user = v
            self.params[f'f{self.adv_num}'] = field
            self.params[f'o{self.adv_num}'] = 'changedby'
            self.params[f'v{self.adv_num}'] = self.service._resuffix(user)
            self.adv_num += 1
            self.options.append(f"{field.capitalize()} changed by: {user}")

        def sort(self, k, v):
            sorting_terms = []
            for x in v:
                inverse = ''
                if x[0] == '-':
                    x = x[1:]
                    inverse = ' DESC'
                try:
                    order_var = self._sorting_map[x]
                except KeyError:
                    choices = ', '.join(sorted(self._sorting_map.keys()))
                    raise BiteError(
                        f'unable to sort by: {x!r} (available choices: {choices}')
                sorting_terms.append(f'{order_var}{inverse}')
            self.params[k] = ','.join(sorting_terms)
            self.options.append(f"Sort order: {', '.join(v)}")

        @alias('blocks', 'depends_on')
        def keywords(self, k, v):
            self.params[k] = v
            self.options.append(f"{self.service.item.attributes[k]}: {', '.join(map(str, v))}")

        @alias('votes')
        def quicksearch(self, k, v):
            self.params[k] = v
            self.options.append(f"{k.capitalize()}: {v}")

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
            saved_search = self.service.saved_searches.get(v)
            if saved_search is None:
                raise BiteError(f'no matching saved search: {v!r}')
            self.options.append(f'Using saved search: {v}')
            for k, v in parse_qs(saved_search['query']).items():
                if k not in self.params:
                    self.params[k] = v if len(v) > 1 else v[0]


class ChangesRequest(BaseChangesRequest, ParseRequest):
    """Construct a changes request."""

    def parse(self, data):
        def items():
            bugs = data['bugs']
            for b in bugs:
                yield tuple(BugzillaEvent(change=x, id=b['id'], alias=b['alias'], count=i)
                            for i, x in enumerate(b['history'], start=1))
        yield from self.filter(items())

    class ParamParser(ParseRequest.ParamParser):

        def _finalize(self):
            if 'ids' not in self.params:
                raise ValueError(f'No {self.service.item.type} ID(s) specified')

        def ids(self, k, v):
            ids = list(map(str, v))
            self.params[k] = ids
            self.options.append(f"IDs: {', '.join(ids)}")

        def created(self, k, v):
            self.params['new_since'] = v.isoformat()
            self.options.append(f'Created: {v} (since {v!r} UTC)')


class CommentsRequest(BaseCommentsRequest, ParseRequest):
    """Construct a comments request."""

    def parse(self, data):
        def items():
            bugs = data['bugs']
            for i in self.params['ids']:
                yield tuple(BugzillaComment(comment=comment, id=i, count=j)
                            for j, comment in enumerate(bugs[i]['comments']))
        yield from self.filter(items())

    class ParamParser(ParseRequest.ParamParser):

        def _finalize(self):
            if 'ids' not in self.params and 'comment_ids' not in self.params:
                raise ValueError(f'No {self.service.item.type} or comment ID(s) specified')

        def ids(self, k, v):
            ids = list(map(str, v))
            self.params[k] = ids
            self.options.append(f"IDs: {', '.join(ids)}")

        def comment_ids(self, k, v):
            comment_ids = list(map(str, v))
            self.params[k] = comment_ids
            self.options.append(f"Comment IDs: {', '.join(comment_ids)}")

        def created(self, k, v):
            self.params['new_since'] = v.isoformat()
            self.options.append(f'Created: {v} (since {v!r} UTC)')

        def fields(self, k, v):
            self.params['include_fields'] = v


class AttachmentsRequest(Request):
    """Construct an attachments request."""

    def __init__(self, ids=None, attachment_ids=None, fields=None,
                 get_data=False, **kw):
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


class ModifyRequest(ParseRequest):
    """Construct a modify request."""

    def parse(self, data):
        return data['bugs']

    @aliased
    class ParamParser(ParseRequest.ParamParser):

        def _finalize(self):
            ids = self.params.pop('ids', None)
            if not ids:
                raise ValueError('No bug ID(s) specified')

            if not self.params:
                raise ValueError('No changes specified')

            self.params['ids'] = ids

            if self.options:
                prefix = '--- Modifying fields '
                self.options.insert(0, prefix + '-' * (const.COLUMNS - len(prefix)))

            if 'comment' in self.params:
                prefix = '--- Adding comment '
                self.options.append(prefix + '-' * (const.COLUMNS - len(prefix)))
                self.options.append(self.params['comment']['body'])

            self.options.append('-' * const.COLUMNS)

        def _default_parser(self, k, v):
            if k in self.service.item.attributes:
                if k == 'assigned_to':
                    v = self.service._resuffix(v)
                self.params[k] = v
                self.options.append('{:<10}: {}'.format(self.service.item.attributes[k], v))
            else:
                super()._default_parser(k, v)

        def ids(self, k, v):
            self.params[k] = v

        # fields that can be added or removed
        @alias('groups', 'see_also', 'cc')
        def _add_remove(self, k, v):
            try:
                remove, add = v
            except ValueError:
                raise ValueError(f"invalid add/remove values for '{k}'")

            if k == 'cc':
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

        # fields that can be added, removed, or set
        @alias('alias', 'blocks', 'depends', 'keywords')
        def _add_remove_set(self, k, v):
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

        @alias('comment_is_private', 'comment_is_markdown')
        def comment(self, k, v):
            if k == 'comment':
                k = 'comment_body'
            key1, key2 = k.split('_', 1)
            self.params.setdefault(key1, {})[key2] = v


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


class CreateRequest(ParseRequest):
    """Construct a bug creation request."""

    # map from standardized kwargs name to expected service parameter name
    _params_map = {
        'milestone': 'target_milestone',
    }

    def parse(self, data):
        return data['id']

    @aliased
    class ParamParser(ParseRequest.ParamParser):

        def __init__(self, **kw):
            super().__init__(**kw)
            self.options.append('=' * const.COLUMNS)

        def _finalize(self):
            # TODO: check param value validity against cached values?
            required_params = {
                'product', 'component', 'version', 'summary', 'op_sys', 'platform'}
            missing_params = required_params - self.params.keys()
            if missing_params:
                raise ValueError(f"missing required params: {', '.join(missing_params)}")

            # make sure description is last in the options output
            if 'description' in self.params:
                msg_prefix = 'Description'
                self.options.append(
                    f'{"-" * 3} {msg_prefix} {"-" * (const.COLUMNS - len(msg_prefix) - 5)}')
                self.options.append(self.params['description'])

            self.options.append('=' * const.COLUMNS)

        def _default_parser(self, k, v):
            if k in self.service.item.attributes:
                self.params[k] = v
                self.options.append('{:<10}: {}'.format(self.service.item.attributes[k], v))
            else:
                super()._default_parser(k, v)

        def assigned_to(self, k, v):
            self.params[k] = list(map(self.service._resuffix, v))
            self.options.append(f"Assigned to: {self.service._desuffix(v)}")

        def cc(self, k, v):
            self.params[k] = list(map(service._resuffix, v))
            self.options.append(f"CC: {', '.join(map(service._desuffix, v))}")

        def milestone(self, k, v):
            self.params[k] = v
            self.options.append(f"Milestone: {v}")

        def description(self, k, v):
            self.params[k] = v


class GetItemRequest(Request):
    """Construct an item retrieval request."""

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
