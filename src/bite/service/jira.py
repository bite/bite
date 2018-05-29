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

    def __init__(self, get_desc=False, **kw):
        for k, v in kw.items():
            if k in ('assignee', 'reporter', 'creator', 'status', 'priority'):
                v = v.get('name') if v else None
            elif k in ('updated', 'created'):
                v = parsetime(v)
            elif k == 'votes':
                v = v.get('votes')
            elif k == 'watches':
                v = v.get('watchCount')
            setattr(self, k, v)

        if get_desc:
            desc = self.description.strip() if self.description else None
            if desc:
                desc = JiraComment(
                    count=0, creator=self.creator, created=self.created, text=desc)
            self.description = desc


class JiraComment(Comment):
    pass


class JiraAttachment(Attachment):
    pass


class JiraEvent(Change):
    pass


class Jira(JsonREST):
    """Service supporting the Jira-based issue trackers."""

    _service = 'jira'

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

    @staticmethod
    def handle_error(code, msg):
        """Handle Jira specific errors."""
        raise JiraError(msg=msg, code=code)


class JiraPagedRequest(OffsetPagedRequest, RESTRequest):

    _offset_key = 'startAt'
    _size_key = 'maxResults'
    _total_key = 'total'


@req_cmd(Jira, cmd='search')
class _SearchRequest(RESTParseRequest, JiraPagedRequest):
    """Construct a search request."""

    def __init__(self, get_desc=False, **kw):
        # use POST requests to avoid URL length issues with massive JQL queries
        self._get_desc = get_desc
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
            yield self.service.item(id=id, get_desc=self._get_desc, **fields)

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

            # if configured for a specific project, limit search to specified project
            if self.service.project:
                jql = f"project = {self.service.project} AND ( {jql} )"

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


@req_cmd(Jira)
class _GetItemRequest(Request):
    """Construct an issue request."""

    def __init__(self, ids, get_desc=True, **kw):
        super().__init__(**kw)
        if ids is None:
            raise ValueError(f'No {self.service.item.type} specified')

        self.ids = list(map(str, ids))
        self.options.append(f"IDs: {', '.join(self.ids)}")

        self._get_desc = get_desc
        reqs = []

        # enable/disable field retrieval and expansion based on requested fields
        params = {}
        expand = []
        fields = ['*all']
        for attr, field in (('comments', 'comment'),
                            ('changes', 'changelog'),
                            ('attachments', 'attachment')):
            if getattr(self, f'_get_{attr}'):
                expand.append(field)
            else:
                fields.append(f'-{field}')

        params['expand'] = expand
        params['fields'] = fields

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
            yield self.service.item(id=id, get_desc=self._get_desc, **fields)


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
            for comments in self._data:
                l = []
                for i, c in enumerate(comments, start=1):
                    l.append(JiraComment(
                        id=c['id'], count=i, creator=c['author']['name'],
                        created=parsetime(c['created']), modified=parsetime(c['updated']),
                        text=c['body'].strip()))
                yield tuple(l)
        else:
            # TODO
            pass


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
                l = []
                for a in attachments:
                    l.append(JiraAttachment(
                        id=a['id'], creator=a['author']['name'],
                        created=parsetime(a['created']), size=a['size'],
                        filename=a['filename'], mimetype=a['mimeType'],
                        url=a['content']))
                yield tuple(l)
        else:
            # TODO
            pass


@req_cmd(Jira, cmd='changes')
class _ChangesRequest(BaseChangesRequest):
    """Construct a comments request."""


@req_cmd(Jira, cmd='get')
class _GetRequest(_GetItemRequest):
    """Construct requests to retrieve all known data for given issue IDs."""

    def __init__(self, get_comments=True, get_attachments=True, get_changes=False, **kw):
        self._get_comments = get_comments
        self._get_attachments = get_attachments
        self._get_changes = get_changes
        super().__init__(get_desc=get_comments, **kw)

    def parse(self, data):
        items = list(super().parse(data))
        comments = self._none_gen
        attachments = self._none_gen
        changes = self._none_gen

        if any((self._get_comments, self._get_attachments, self._get_changes)):
            if self._get_comments:
                item_descs = ((x.description,) if x.description else () for x in items)
                item_comments = (x.comment['comments'] for x in items)
                item_comments = self.service.CommentsRequest(
                    ids=self.ids, data=item_comments).send()
                comments = (x + y for x, y in zip(item_descs, item_comments))
            if self._get_attachments:
                item_attachments = (getattr(x, 'attachment', ()) for x in items)
                attachments = self.service.AttachmentsRequest(
                    ids=self.ids, data=item_attachments).send()
            if self._get_changes:
                item_changes = (x.changelog for x in items)
                changes = self.service.ChangesRequest(
                    ids=self.ids, data=item_changes).send()

        for item in items:
            item.comments = next(comments)
            item.attachments = next(attachments)
            item.changes = next(changes)
            yield item
