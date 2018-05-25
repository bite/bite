"""Support Redmine's REST interface.

API docs:
    - http://www.redmine.org/projects/redmine/wiki/Rest_api
"""

from functools import partial

from dateutil.parser import parse as dateparse

from .._reqs import OffsetPagedRequest, ParseRequest, Request, req_cmd
from .._rest import REST, RESTRequest
from ...exceptions import BiteError, RequestError
from ...objects import Item, Comment, Attachment, Change


class RedmineError(RequestError):
    """Redmine service specific error."""

    def __init__(self, msg, code=None, text=None):
        msg = f'Redmine error: {msg}'
        super().__init__(msg, code, text)


class RedmineIssue(Item):

    attributes = {
        'id': 'ID',
    }

    attribute_aliases = {
        'title': 'subject',
        'created': 'created_on',
        'modified': 'updated_on',
        'owner': 'assigned_to',
    }

    _print_fields = (
        ('subject', 'Title'),
        ('assigned_to', 'Assignee'),
        ('created_on', 'Created'),
        ('updated_on', 'Modified'),
        ('closed_on', 'Closed'),
        ('author', 'Reporter'),
        ('id', 'ID'),
        ('status', 'Status'),
        ('priority', 'Priority'),
    )

    type = 'issue'

    def __init__(self, service, get_desc=False, **kw):
        # TODO: clean up item initialization
        # initialize fields that can be blank so the service won't return them
        self.closed_on = None
        self.assigned_to = None

        for k, v in kw.items():
            # strip "Bug #ID (status): " prefix from titles
            if k == 'title':
                v = v.partition(': ')[2]
            elif k in ('created_on', 'updated_on', 'closed_on',):
                v = dateparse(v)
            elif k in ('author', 'assigned_to', 'status', 'priority'):
                v = v['name']

            if k == 'custom_fields':
                for field in v:
                    setattr(self, field['name'], field['value'])
            else:
                setattr(self, k, v)

        if get_desc:
            self.description = RedmineComment(
                count=0, creator=self.author, created=self.created_on, text=self.description.strip())


class RedmineComment(Comment):
    pass


class RedmineAttachment(Attachment):
    pass


class RedmineEvent(Change):
    pass


class Redmine(REST):
    """Service supporting the Redmine-based issue trackers."""

    item = RedmineIssue
    item_endpoint = '/issues/{id}'

    def __init__(self, base, max_results=None, **kw):
        try:
            api_base, project = base.split('/projects/', 1)
        except ValueError as e:
            raise BiteError(f'invalid project base: {base!r}')

        # most redmine instances default to 100 results per query
        if max_results is None:
            max_results = 100
        super().__init__(base=base, max_results=max_results, **kw)

        self._project = project
        self.webbase = api_base

    def inject_auth(self, request, params):
        raise NotImplementedError

    @staticmethod
    def handle_error(code, msg):
        """Handle Redmine specific errors."""
        raise RedmineError(msg=msg, code=code)


class RedmineElastic(Redmine):
    """Service supporting the Redmine-based issue trackers with elasticsearch plugin."""


class RedminePagedRequest(OffsetPagedRequest, RESTRequest):

    _offset_key = 'offset'
    _size_key = 'limit'
    _total_key = 'total_count'


@req_cmd(Redmine)
class _GetItemRequest(RESTRequest):
    """Construct an issue request."""

    def __init__(self, service, ids, get_desc=True, **kw):
        if ids is None:
            raise ValueError(f'No {service.item.type} ID(s) specified')

        endpoint = f"/issues.{service._ext}?status_id=*&issue_id={','.join(map(str, ids))}"
        super().__init__(service=service, endpoint=endpoint, **kw)

        self.ids = ids
        self._get_desc = get_desc

    def parse(self, data):
        issues = data['issues']
        for issue in issues:
            yield self.service.item(self.service, get_desc=self._get_desc, **issue)


@req_cmd(Redmine)
class _CommentsRequest(Request):
    """Construct a comments request."""

    def __init__(self, ids, **kw):
        super().__init__(**kw)
        if ids is None:
            raise ValueError(f'No {self.service.item.type} ID(s) specified')

        reqs = []
        for i in ids:
            reqs.append(RESTRequest(
                service=self.service,
                endpoint=f'{self.service.webbase}/issues/{i}.{self.service._ext}?include=journals'))

        self.ids = ids
        self._reqs = tuple(reqs)

    def parse(self, data):
        for x in data:
            events = x['issue']['journals']
            count = 1
            l = []
            for c in events:
                notes = c.get('notes', None)
                if not notes:
                    continue
                l.append(RedmineComment(
                    id=c['id'], count=count, creator=c['user']['name'],
                    created=dateparse(c['created_on']), text=notes.strip()))
                count += 1
            yield tuple(l)


@req_cmd(Redmine, cmd='get')
class _GetRequest(_GetItemRequest):
    """Construct requests to retrieve all known data for given issue IDs."""

    def __init__(self, get_comments=True, get_attachments=True, get_changes=False, **kw):
        super().__init__(**kw)
        self._get_comments = get_comments
        self._get_attachments = get_attachments
        self._get_changes = get_changes

    def parse(self, data):
        items = list(super().parse(data))
        comments = self._none_gen
        attachments = self._none_gen
        changes = self._none_gen

        if any((self._get_comments, self._get_attachments, self._get_changes)):
            ids = [x.id for x in items]
            if self._get_comments:
                item_descs = ((x.description,) for x in items)
                item_comments = self.service.CommentsRequest(ids=ids).send()
                comments = (x + y for x, y in zip(item_descs, item_comments))

        for item in items:
            item.comments = next(comments)
            item.attachments = next(attachments)
            item.changes = next(changes)
            yield item


class _BaseSearchRequest(ParseRequest, RedminePagedRequest):
    """Construct a search request."""

    def __init__(self, *, service, **kw):
        super().__init__(service=service, endpoint=f'/search.{service._ext}', **kw)

    def parse(self, data):
        data = super().parse(data)
        # pull additional issue fields not returned in search results
        issues = self.service.GetItemRequest(ids=[x['id'] for x in data['results']]).send()
        yield from issues


@req_cmd(Redmine, cmd='search')
class _SearchRequest(_BaseSearchRequest):
    """Construct a search request."""

    class ParamParser(ParseRequest.ParamParser):

        def __init__(self, **kw):
            super().__init__(**kw)
            self.query = {}

        def _finalize(self, **kw):
            if not self.query:
                raise BiteError('no supported search terms or options specified')

            self.params['q'] = ' AND '.join(self.query.values())

            # only return issues
            self.params['issues'] = 1

            # return all non-closed issues by default
            if 'status' not in self.params:
                self.params['open_issues'] = 1

            # only search titles by default
            self.params['titles_only'] = 1

        def terms(self, k, v):
            self.query['summary'] = '+'.join(v)
            self.options.append(f"Summary: {', '.join(map(str, v))}")


@req_cmd(RedmineElastic, name='SearchRequest', cmd='search')
class _ElasticSearchRequest(ParseRequest, RedminePagedRequest):
    """Construct an elasticsearch compatible search request.

    Assumes the elasticsearch plugin is installed:
        http://www.redmine.org/plugins/redmine_elasticsearch
        https://github.com/Restream/redmine_elasticsearch/wiki/Search-Quick-Reference
    """

    def __init__(self, *, service, **kw):
        super().__init__(service=service, endpoint=f'/search.{service._ext}', **kw)

    def parse(self, data):
        data = super().parse(data)
        # pull additional issue fields not returned in search results
        ids = [x['id'] for x in data['results']]
        issues = self.service.GetItemRequest(ids=ids).send()
        yield from issues

    class ParamParser(ParseRequest.ParamParser):

        def __init__(self, **kw):
            super().__init__(**kw)
            self.query = {}

        def _finalize(self, **kw):
            if not self.query:
                raise BiteError('no supported search terms or options specified')

            # return all non-closed issues by default
            if 'status' not in self.query:
                self.params['open_issues'] = 1

            query_string = ' AND '.join(self.query.values())
            self.params['q'] = f'_type:issue AND ({query_string})'

        def terms(self, k, v):
            or_queries = []
            display_terms = []
            for term in v:
                or_terms = [x.replace('"', '\\"') for x in term.split(',')]
                or_search_terms = [f'title:"{x}"' for x in or_terms]
                or_display_terms = [f'"{x}"' for x in or_terms]
                if len(or_terms) > 1:
                    or_queries.append(f"({' OR '.join(or_search_terms)})")
                    display_terms.append(f"({' OR '.join(or_display_terms)})")
                else:
                    or_queries.append(or_search_terms[0])
                    display_terms.append(or_display_terms[0])
            self.query['summary'] = f"{' AND '.join(or_queries)}"
            self.options.append(f"Summary: {' AND '.join(display_terms)}")

        def status(self, k, v):
            self.query['status'] = f"status:({' OR '.join(v)})"
            self.options.append(f"Status: {', '.join(v)}")
