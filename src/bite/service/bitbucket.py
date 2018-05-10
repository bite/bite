"""Support Bitbucket's REST interface.

API docs:
    https://api.bitbucket.org/
    https://developer.atlassian.com/cloud/bitbucket/

Updates:
    https://blog.bitbucket.org/
"""

from dateutil.parser import parse as dateparse

from ._jsonrest import JsonREST
from ._reqs import (
    RESTRequest, LinkPagedRequest, Request, GetRequest, ParseRequest,
    generator, req_cmd,
)
from ..exceptions import BiteError, RequestError
from ..objects import Item, Comment, Attachment, Change


class BitbucketError(RequestError):
    """Bitbucket service specific error."""

    def __init__(self, msg, code=None, text=None):
        msg = f'Bitbucket error: {msg}'
        super().__init__(msg, code, text)


class BitbucketIssue(Item):

    attributes = {
        'assignee': 'Assignee',
        'id': 'ID',
        'title': 'Title',
        'kind': 'Type',
        'priority': 'Priority',
        'reporter': 'Reporter',
        'component': 'Component',
        'votes': 'Votes',
        'watches': 'Watches',
        'state': 'Status',
        'version': 'Version',
        #'edited_on': 'Edited',
        'created_on': 'Created',
        'updated_on': 'Modified',
    }

    attribute_aliases = {
        'owner': 'assignee',
        'created': 'created_on',
        'modified': 'updated_on',
        'creator': 'reporter',
        'status': 'state',
    }

    _print_fields = (
        ('assignee', 'Assignee'),
        ('title', 'Title'),
        ('id', 'ID'),
        ('kind', 'Type'),
        ('priority', 'Priority'),
        ('reporter', 'Reporter'),
        ('component', 'Component'),
        ('state', 'Status'),
        ('version', 'Version'),
        ('created_on', 'Created'),
        ('updated_on', 'Modified'),
        ('votes', 'Votes'),
        ('watches', 'Watches'),
        ('comments', 'Comments'),
        ('attachments', 'Attachments'),
        ('changes', 'Changes'),
    )

    type = 'issue'

    def __init__(self, service, issue, get_desc=True):
        for k in self.attributes.keys():
            v = issue.get(k, None)
            if k in ('assignee', 'reporter') and v:
                v = v['username']
            elif k == 'reporter' and v is None:
                v = 'Anonymous'
            elif k in ('created_on', 'updated_on'):
                v = dateparse(v)
            setattr(self, k, v)

        if get_desc:
            try:
                desc = issue['content']['raw'].strip()
            except KeyError:
                desc = ''
            self.description = BitbucketComment(
                count=0, text=desc, created=self.created_on, creator=self.reporter)


class BitbucketComment(Comment):
    pass


class BitbucketAttachment(Attachment):
    pass


class BitbucketEvent(Change):

    def __init__(self, service, id, count, change):
        creator = change['user']
        if creator is not None:
            creator = creator['username']
        created = dateparse(change['created_on'])
        changes = {}
        for k, v in change['changes'].items():
            if k == 'content':
                changes['description'] = 'updated'
            else:
                changes[service.item.attributes.get(k, k)] = (v['old'], v['new'])

        super().__init__(
            creator=creator, created=created, id=id,
            changes=changes, count=count)


class Bitbucket(JsonREST):
    """Service supporting the Bitbucket-based issue trackers."""

    _service = 'bitbucket'

    item = BitbucketIssue
    item_endpoint = '/issues/{id}'
    attachment = BitbucketAttachment

    def __init__(self, base, max_results=None, **kw):
        try:
            api_base, user, repo = base.rstrip('/').rsplit('/', 2)
        except ValueError as e:
            raise BiteError(f'invalid project base: {base!r}')
        self._api_base = f'{api_base}/api/2.0'
        endpoint = f'/repositories/{user}/{repo}'
        # bitbucket cloud supports 100 results per page
        if max_results is None:
            max_results = 100
        # TODO: generalize and allow versioned API support
        super().__init__(
            endpoint=endpoint, base=self._api_base, max_results=max_results, **kw)
        self.webbase = base

    def inject_auth(self, request, params):
        raise NotImplementedError

    def parse_response(self, response):
        data = super().parse_response(response)
        if data.get('type', None) != 'error':
            return data
        else:
            self.handle_error(code=response.status_code, msg=data['error']['message'])

    @staticmethod
    def handle_error(code, msg):
        """Handle Bitbucket specific errors."""
        raise BitbucketError(msg=msg, code=code)


class BitbucketPagedRequest(RESTRequest, LinkPagedRequest):

    _page = 'page'
    _pagelen = 'pagelen'
    _next = 'next'
    _previous = 'previous'
    _total_key = 'size'


@req_cmd(Bitbucket, cmd='search')
class _SearchRequest(BitbucketPagedRequest, ParseRequest):
    """Construct a search request."""

    def __init__(self, *args, **kw):
        super().__init__(*args, endpoint='/issues', **kw)

    def parse(self, data):
        super().parse(data)
        issues = data['values']
        for issue in issues:
            yield self.service.item(self.service, issue)

    class ParamParser(ParseRequest.ParamParser):

        # Map of allowed sorting input values to service parameters.
        _sorting_map = {
            'assignee': 'assignee',
            'id': 'id',
            'title': 'title',
            'type': 'kind',
            'priority': 'priority',
            'creator': 'reporter',
            'component': 'component',
            'votes': 'votes',
            'watches': 'watches',
            'status': 'state',
            'version': 'version',
            'created': 'created_on',
            'modified': 'updated_on',
            'description': 'content',
        }

        def __init__(self, request):
            super().__init__(request)
            self.query = {}

        def _finalize(self, **kw):
            if not self.query:
                raise BiteError('no supported search terms or options specified')

            self.params['q'] = ' AND '.join(self.query.values())

            # sort ascending by issue ID by default
            if 'sort' not in self.params:
                self.params['sort'] = 'id'

        def terms(self, k, v):
            or_queries = []
            display_terms = []
            for term in v:
                or_terms = [x.replace('"', '\\"') for x in term.split(',')]
                or_search_terms = [f'title ~ "{x}"' for x in or_terms]
                or_display_terms = [f'"{x}"' for x in or_terms]
                if len(or_terms) > 1:
                    or_queries.append(f"({' OR '.join(or_search_terms)})")
                    display_terms.append(f"({' OR '.join(or_display_terms)})")
                else:
                    or_queries.append(or_search_terms[0])
                    display_terms.append(or_display_terms[0])
            self.query['summary'] = f"{' AND '.join(or_queries)}"
            self.options.append(f"Summary: {' AND '.join(display_terms)}")

        def sort(self, k, v):
            if v[0] == '-':
                key = v[1:]
                inverse = '-'
            else:
                key = v
                inverse = ''
            try:
                order_var = self._sorting_map[key]
            except KeyError:
                choices = ', '.join(sorted(self._sorting_map.keys()))
                raise BiteError(
                    f'unable to sort by: {key!r} (available choices: {choices}')
            self.params['sort'] = f'{inverse}{order_var}'
            self.options.append(f"Sort order: {v}")


@req_cmd(Bitbucket)
class _GetItemRequest(Request):
    """Construct an issue request."""

    def __init__(self, ids, get_desc=True, **kw):
        super().__init__(**kw)
        if ids is None:
            raise ValueError(f'No {self.service.item.type} ID(s) specified')

        reqs = []
        for i in ids:
            reqs.append(RESTRequest(
                service=self.service, endpoint=f'/issues/{i}'))

        self.ids = ids
        self._reqs = tuple(reqs)
        self._get_desc = get_desc

    def parse(self, data):
        # TODO: hack, rework the http send parsing rewapper to be more
        # intelligent about unwrapping responses
        if len(self.ids) == 1:
            data = [data]
        for issue in data:
            yield self.service.item(self.service, issue, get_desc=self._get_desc)


@req_cmd(Bitbucket, cmd='comments')
class _CommentsRequest(Request):
    """Construct a comments request."""

    def __init__(self, ids=None, **kw):
        super().__init__(**kw)
        if ids is None:
            raise ValueError(f'No {self.service.item.type} ID(s) specified')

        reqs = []
        for i in ids:
            reqs.append(BitbucketPagedRequest(
                service=self.service, endpoint=f'/issues/{i}/comments'))

        self.ids = ids
        self._reqs = tuple(reqs)

    @generator
    def parse(self, data):
        # skip comments that have no content, i.e. issue attribute changes
        for i in self.ids:
            comments = next(data)['values']
            l = []
            for j, c in enumerate(comments):
                creator = c['user']
                if creator is not None:
                    creator = creator['username']
                if c['content']['raw']:
                    l.append(BitbucketComment(
                        id=i, count=j+1, text=c['content']['raw'].strip(),
                        created=dateparse(c['created_on']), creator=creator))
            yield tuple(l)


@req_cmd(Bitbucket, cmd='attachments')
class _AttachmentsRequest(Request):
    """Construct an attachments request."""

    def __init__(self, ids=None, get_data=False, *args, **kw):
        super().__init__(**kw)
        if ids is None:
            raise ValueError(f'No {self.service.item.type} ID(s) specified')

        reqs = []
        for i in ids:
            reqs.append(BitbucketPagedRequest(
                service=self.service, endpoint=f'/issues/{i}/attachments'))

        self.ids = ids
        self._reqs = tuple(reqs)

    @generator
    def parse(self, data):
        for attachments in data:
            attachments = attachments['values']
            yield tuple(
                self.service.attachment(
                    filename=a['name'], url=a['links']['self']['href'])
                for a in attachments)


@req_cmd(Bitbucket, cmd='changes')
class _ChangesRequest(Request):
    """Construct a changes request."""

    def __init__(self, ids=None, **kw):
        super().__init__(**kw)
        if ids is None:
            raise ValueError(f'No {self.service.item.type} ID(s) specified')

        reqs = []
        for i in ids:
            reqs.append(BitbucketPagedRequest(
                service=self.service, endpoint=f'/issues/{i}/changes'))

        self.ids = ids
        self._reqs = tuple(reqs)

    @generator
    def parse(self, data):
        for i in self.ids:
            changes = next(data)['values']
            yield tuple(BitbucketEvent(self.service, id=c['id'], count=j, change=c)
                   for j, c in enumerate(changes))


@req_cmd(Bitbucket, cmd='get')
class _GetRequest(GetRequest):
    """Construct requests to retrieve all known data for given issue IDs."""

    def __init__(self, *args, get_comments=False, **kw):
        super().__init__(*args, get_comments=get_comments, **kw)
        self.get_comments = get_comments

    def parse(self, data):
        items, comments, attachments, changes = data
        for item in items:
            # Prepend comment for description which is provided by
            # GetItemRequest instead of CommentsRequest.
            if self.get_comments:
                item.comments = (item.description,) + next(comments)
            else:
                item.comments = None
            item.attachments = next(attachments)
            item.changes = next(changes)
            yield item
