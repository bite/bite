"""Support JIRA's REST interface.

API docs:
    - https://developer.atlassian.com/server/jira/platform/rest-apis/
    - https://docs.atlassian.com/jira/REST/server/
"""

import re

from dateutil.parser import parse as parsetime
from snakeoil.klass import aliased, alias

from ._jsonrest import JsonREST
from ._reqs import (
    OffsetPagedRequest, req_cmd, BaseCommentsRequest, BaseChangesRequest,
    NullRequest, Request
)
from ._rest import RESTRequest, RESTParseRequest
from ..exceptions import BiteError, RequestError
from ..objects import Item, Comment, Change, Attachment


class JiraError(RequestError):
    """Jira service specific error."""

    def __init__(self, msg, code=None, text=None):
        msg = f'Jira error: {msg}'
        super().__init__(msg, code, text)


class JiraIssue(Item):

    attributes = {
        'created': 'Created',
        'updated': 'Modified',
    }

    attribute_aliases = {
        'title': 'summary',
        'owner': 'assignee',
    }

    _print_fields = (
        ('assignee', 'Assignee'),
        ('summary', 'Title'),
        ('id', 'ID'),
        ('priority', 'Priority'),
        ('reporter', 'Reporter'),
        ('creator', 'Creator'),
        ('status', 'Status'),
        ('created', 'Created'),
        ('updated', 'Modified'),
        ('votes', 'Votes'),
        ('watches', 'Watchers'),
        ('comments', 'Comments'),
        ('attachments', 'Attachments'),
        ('changes', 'Changes'),
    )

    type = 'issue'

    def __init__(self, get_comments=False, get_attachments=False, get_changes=False, **kw):
        # TODO: add support for parsing changes
        self.changes = None
        self.attachments = None
        self.comments = None

        for k, v in kw.items():
            if k in ('assignee', 'reporter', 'creator', 'status', 'priority'):
                v = v.get('name') if v else None
            elif k in ('updated', 'created'):
                v = parsetime(v)
            elif k == 'votes':
                v = v.get('votes')
            elif k == 'watches':
                v = v.get('watchCount')
            elif k == 'attachment' and get_attachments:
                k = 'attachments'
                v = JiraAttachment.parse(v)
            elif k == 'comment' and get_comments:
                k = 'comments'
                v = JiraComment.parse(v['comments'])
            setattr(self, k, v)

        if get_comments:
            desc = self.description.strip() if self.description else None
            if desc:
                desc = JiraComment(
                    count=0, creator=self.creator, created=self.created, text=desc)
            self.description = desc
            if self.description:
                self.comments = (self.description,) + self.comments


class JiraComment(Comment):

    @classmethod
    def parse(cls, data):
        l = []
        for i, c in enumerate(data, start=1):
            # don't count creation as a modification
            updated = parsetime(c['updated']) if c['updated'] != c['created'] else None

            l.append(cls(
                id=c['id'], count=i, creator=c['author']['name'],
                created=parsetime(c['created']), modified=updated,
                text=c['body'].strip()))
        return tuple(l)


class JiraAttachment(Attachment):

    @classmethod
    def parse(cls, data):
        l = []
        for a in data:
            l.append(cls(
                id=a['id'], creator=a['author']['name'],
                created=parsetime(a['created']), size=a['size'],
                filename=a['filename'], mimetype=a['mimeType'],
                url=a['content']))
        return tuple(l)


class JiraEvent(Change):
    pass


class Jira(JsonREST):
    """Service supporting the Jira-based issue trackers."""

    _service = 'jira'
    _service_error_cls = JiraError

    item = JiraIssue
    _item_endpoint = '/browse/{project}-{{id}}'
    attachment_endpoint = '/secure/attachment/{id}'

    def __init__(self, base, max_results=None, **kw):
        try:
            api_base, _sep, project = base.partition('/projects/')
            project = project.strip('/')
        except ValueError as e:
            raise BiteError(f'invalid project base: {base!r}')
        self.project = project if project else None
        # most jira instances default to 1k results per query
        if max_results is None:
            max_results = 1000
        # TODO: generalize and allow versioned API support
        super().__init__(
            endpoint=f"/rest/api/2", base=api_base, max_results=max_results, **kw)
        self.webbase = api_base

    @property
    def item_endpoint(self):
        """Allow the item endpoint to be dynamically altered by changing the project attr."""
        if self.project:
            return self._item_endpoint.format(project=self.project)
        return self._item_endpoint

    def _format_item_urls(self, url, ids):
        """Format item URLs from given information.

        This adds support for conglomerate connections that have to add the
        project IDs to the requested ID.
        """
        for i in ids:
            if isinstance(i, str):
                project, _sep, id = i.partition('-')
                if not all((project, id)):
                    raise BiteError(f'invalid item ID missing project or item number: {i!r}')
                url = url.format(project=project)
                i = id
            yield url.format(id=i)

    def inject_auth(self, request, params):
        raise NotImplementedError

    def parse_response(self, response):
        data = super().parse_response(response)
        if 'errorMessages' not in data:
            return data
        else:
            self.handle_error(code=response.status_code, msg=data['errorMessages'][0])


class JiraPagedRequest(OffsetPagedRequest, RESTRequest):

    _offset_key = 'startAt'
    _size_key = 'maxResults'
    _total_key = 'total'


@req_cmd(Jira, cmd='search')
class _SearchRequest(RESTParseRequest, JiraPagedRequest):
    """Construct a search request."""

    def __init__(self, **kw):
        # use POST requests to avoid URL length issues with massive JQL queries
        super().__init__(endpoint='/search', method='POST', **kw)

    def parse(self, data):
        data = super().parse(data)
        issues = data['issues']
        for issue in issues:
            # Use project ID key for issue id, the regular id field relates to
            # the global issue ID across all projects on the service instance.
            # Using the key value matches what is shown on the web interface.
            id = issue.get('key')
            if self.service.project:
                # if configured for a specific project, strip it from the ID
                id = id[len(self.service.project) + 1:]
            fields = issue.get('fields', {})
            yield self.service.item(id=id, **fields)

    @aliased
    class ParamParser(RESTParseRequest.ParamParser):

        # date field key map
        _date_fields = {
            'modified': 'updated',
            'viewed': 'lastViewed',
        }

        def _finalize(self, **kw):
            if not self.params or self.params.keys() == {'sort'}:
                raise BiteError('no supported search terms or options specified')

            # limit fields by default to decrease requested data size and speed up response
            if 'fields' not in self.params:
                self.params['fields'] = ['id', 'assignee', 'summary']

            jql = ' AND '.join(self.params['jql'])

            # default to sorting ascending by ID for search reqs
            sort = self.params.pop('sort', ['id'])
            jql += f" order by {', '.join(sort)}"

            self.params['jql'] = jql
            self.request.fields = self.params['fields']

        def id(self, k, v):
            id_strs = list(map(str, v))
            # convert to ID keys
            id_keys = []
            for i in id_strs:
                if re.match(r'\d+', i) and self.service.project:
                    id_keys.append(f'{self.service.project}-{i}')
                else:
                    id_keys.append(i)
            self.params.setdefault('jql', []).append(f"{k} in ({','.join(id_keys)})")
            self.options.append(f"IDs: {', '.join(id_strs)}")

        def fields(self, k, v):
            # TODO: add service attrs
            # unknown_fields = set(v).difference(self.service.item.attributes.keys())
            # if unknown_fields:
            #     raise BiteError(f"unknown fields: {', '.join(unknown_fields)}")
            self.params[k] = v
            self.options.append(f"Fields: {' '.join(v)}")

        def attachments(self, k, v):
            val = 'not empty' if v else 'empty'
            display_val = 'yes' if v else 'no'
            self.params.setdefault('jql', []).append(f'{k} is {val}')
            self.options.append(f"{k.capitalize()}: {display_val}")

        def project(self, k, v):
            contain = []
            not_contain = []
            for x in v:
                if x[0] == '!':
                    not_contain.append(x[1:])
                else:
                    contain.append(x)

            if contain:
                self.params.setdefault('jql', []).append(f"project in ({','.join(contain)})")
            if not_contain:
                self.params.setdefault('jql', []).append(f"project not in ({','.join(not_contain)})")

            if self.service.project is None or len(v) > 1 or (len(v) == 1 and self.service.project != v[0]):
                self.options.append(f"Project: {', '.join(v)}")

        def terms(self, k, v):
            for term in v:
                self.params.setdefault('jql', []).append(f'summary ~ "{term}"')
            self.options.append(f"Summary: {', '.join(map(str, v))}")

        @alias('modified', 'viewed', 'resolved')
        def created(self, k, v):
            field = self._date_fields.get(k, k)
            if v.start is not None:
                time_str = v.start.strftime('%Y-%m-%d %H:%M')
                self.params.setdefault('jql', []).append(f'{field} > "{time_str}"')
            if v.end is not None:
                time_str = v.end.strftime('%Y-%m-%d %H:%M')
                self.params.setdefault('jql', []).append(f'{field} < "{time_str}"')
            self.options.append(f'{k.capitalize()}: {v} ({v!r} UTC)')

        @alias('creator')
        def assigned_to(self, k, v):
            field = 'assignee' if k == 'assigned_to' else 'reporter'
            self.params.setdefault('jql', []).append(f"{field} in ({','.join(v)})")
            self.options.append(f"{field.capitalize()}: {', '.join(map(str, v))}")

        @alias('watchers')
        def votes(self, k, v):
            if v.start is not None:
                self.params.setdefault('jql', []).append(f'{k} >= {v.start}')
            if v.end is not None:
                self.params.setdefault('jql', []).append(f'{k} <= {v.end}')
            self.options.append(f"{k.capitalize()}: {v} ({v!r} {k})")


@req_cmd(Jira, cmd='get')
class _GetRequest(Request):
    """Construct an issue request."""

    def __init__(self, ids, get_comments=True, get_attachments=True,
                 get_changes=False, **kw):
        super().__init__(**kw)
        if ids is None:
            raise ValueError(f'No {self.service.item.type} specified')

        self._get_comments = get_comments
        self._get_attachments = get_attachments
        self._get_changes = get_changes
        self.ids = list(map(str, ids))
        self.options.append(f"IDs: {', '.join(self.ids)}")

        # enable/disable field retrieval and expansion based on requested fields
        self.item_params = {}
        params = {}
        expand = []
        fields = ['*all']
        for attr, field in (('get_comments', 'comment'),
                            ('get_changes', 'changelog'),
                            ('get_attachments', 'attachment')):
            enabled = getattr(self, f'_{attr}')
            self.item_params[attr] = enabled
            if enabled:
                expand.append(field)
            else:
                fields.append(f'-{field}')

        params['expand'] = expand
        params['fields'] = fields

        reqs = []
        for i in self.ids:
            if re.match(r'\d+', i) and self.service.project:
                id_key = f'{self.service.project}-{i}'
            else:
                id_key = i
            endpoint = f'{self.service._base}/issue/{id_key}'
            reqs.append(RESTRequest(service=self.service, endpoint=endpoint, params=params))
        self._reqs = tuple(reqs)

    def parse(self, data):
        data = super().parse(data)
        for issue in data:
            # Use project ID key for issue id, the regular id field relates to
            # the global issue ID across all projects on the service instance.
            # Using the key value matches what is shown on the web interface.
            id = issue.get('key')
            if self.service.project:
                # if configured for a specific project, strip it from the ID
                id = id[len(self.service.project) + 1:]
            fields = issue.get('fields', {})
            yield self.service.item(id=id, **self.item_params, **fields)


class _SearchGetItemRequest(_SearchRequest):
    """Construct an issue request using a search request.

    Note that the returned items are not in the same order the specified IDs
    are in and Jira currently doesn't seem to support ordering them in that fashion.
    """

    def __init__(self, ids, **kw):
        if ids is None:
            raise ValueError(f'No {self.service.item.type} specified')

        super().__init__(id=ids, **kw)

        self.options.append(f"IDs: {', '.join(map(str, ids))}")
        self.ids = list(map(str, ids))

    class ParamParser(_SearchRequest.ParamParser):

        def _finalize(self, **kw):
            expand = []
            fields = ['*all']

            # enable/disable field retrieval and expansion based on requested fields
            for attr, field in (('comments', 'comment'),
                                ('changes', 'changelog'),
                                ('attachments', 'attachment')):
                if getattr(self.request, f'_get_{attr}'):
                    expand.append(field)
                else:
                    fields.append(f'-{field}')

            self.params['expand'] = expand
            self.params['fields'] = fields
            super()._finalize(**kw)


@req_cmd(Jira, cmd='comments')
class _CommentsRequest(BaseCommentsRequest):
    """Construct a comments request."""

    def __init__(self, **kw):
        super().__init__(**kw)

        if self.ids is None:
            raise ValueError(f'No {self.service.item.type} ID(s) specified')
        self.options.append(f"IDs: {', '.join(self.ids)}")

        reqs = []
        for i in self.ids:
            if re.match(r'\d+', i) and self.service.project:
                id_key = f'{self.service.project}-{i}'
            else:
                id_key = i
            endpoint = f'{self.service._base}/issue/{id_key}/comment'
            reqs.append(JiraPagedRequest(service=self.service, endpoint=endpoint))
        self._reqs = tuple(reqs)

    def parse(self, data):
        def items():
            for x in data:
                yield JiraComment.parse(x['comments'])
        yield from self.filter(items())


@req_cmd(Jira, cmd='attachments')
class _AttachmentsRequest(Request):
    """Construct an attachments request."""

    def __init__(self, ids=None, item_id=False, data=None, **kw):
        super().__init__(**kw)
        if ids is None:
            raise ValueError(f'No ID(s) specified')

        if data is None:
            # TODO
            pass
        else:
            reqs = [NullRequest()]

        self.ids = ids
        self._reqs = tuple(reqs)
        self._data = data

    def parse(self, data):
        if self._data is not None:
            for attachments in self._data:
                yield JiraAttachment.parse(attachments)
        else:
            # TODO
            pass


@req_cmd(Jira, cmd='changes')
class _ChangesRequest(BaseChangesRequest):
    """Construct a comments request."""



@req_cmd(Jira, cmd='version')
class VersionRequest(RESTRequest):
    """Construct a version request."""

    def __init__(self, **kw):
        super().__init__(endpoint='/serverInfo', **kw)

    def parse(self, data):
        return data['version']
