"""Support Bitbucket's REST interface.

API docs:
    https://api.bitbucket.org/
    https://developer.atlassian.com/cloud/bitbucket/

Updates:
    https://blog.bitbucket.org/
"""

from dateutil.parser import parse as dateparse
from snakeoil.klass import aliased, alias

from ._jsonrest import JsonREST
from ._reqs import (
    LinkPagedRequest, Request, req_cmd,
    BaseGetRequest, BaseCommentsRequest, BaseChangesRequest,
)
from ._rest import RESTRequest, RESTParseRequest
from ..exceptions import BiteError, RequestError
from ..objects import Item, Comment, Attachment, Change


class BitbucketError(RequestError):
    """Bitbucket service specific error."""

    def __init__(self, msg, code=None, text=None):
        self.orig_msg = msg
        prefixed_msg = f'Bitbucket error: {msg}'
        super().__init__(msg=prefixed_msg, code=code, text=text)


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
        'watches': 'Watchers',
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
        ('watches', 'Watchers'),
        ('comments', 'Comments'),
        ('attachments', 'Attachments'),
        ('changes', 'Changes'),
    )

    type = 'issue'

    def __init__(self, service, issue, get_desc=True):
        for k in self.attributes.keys():
            v = issue.get(k)
            if k in ('assignee', 'reporter') and v:
                v = v['username']
            elif k == 'reporter' and v is None:
                v = 'Anonymous'
            elif k in ('created_on', 'updated_on'):
                v = dateparse(v)
            elif k == 'component':
                v = v['name']
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
        if data.get('type') != 'error':
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
class _SearchRequest(RESTParseRequest, BitbucketPagedRequest):
    """Construct a search request."""

    # map from standardized kwargs name to expected service parameter name
    _params_map = {
        'created': 'created_on',
        'modified': 'updated_on',
        'watchers': 'watches',
    }

    def __init__(self, **kw):
        super().__init__(endpoint='/issues', **kw)

    def parse(self, data):
        data = super().parse(data)
        issues = data['values']
        for issue in issues:
            yield self.service.item(self.service, issue)

    @aliased
    class ParamParser(RESTParseRequest.ParamParser):

        # map of allowed sorting input values to service parameters
        _sorting_map = {
            'assignee': 'assignee',
            'id': 'id',
            'title': 'title',
            'type': 'kind',
            'priority': 'priority',
            'creator': 'reporter',
            'component': 'component',
            'votes': 'votes',
            'watchers': 'watches',
            'status': 'state',
            'version': 'version',
            'created': 'created_on',
            'modified': 'updated_on',
            'description': 'content',
        }

        # map of allowed priority input values to service parameters
        _priority_map = {
            'trivial': 'trivial',
            'minor': 'minor',
            'major': 'major',
            'critical': 'critical',
            'blocker': 'blocker',
        }

        # map of allowed type input values to service parameters
        _type_map = {
            'bug': 'bug',
            'enhancement': 'enhancement',
            'proposal': 'proposal',
            'task': 'task',
        }

        # map of allowed status input values to service parameters
        _status_map = {
            'new': 'new',
            'open': 'open',
            'resolved': 'resolved',
            'on-hold': 'on hold',
            'invalid': 'invalid',
            'duplicate': 'duplicate',
            'wontfix': 'wontfix',
            'closed': 'closed',
        }

        # map of status alias names to matching status values
        _status_aliases = {
            'OPEN': ('new', 'open', 'on hold'),
            'CLOSED': ('resolved', 'invalid', 'duplicate', 'wontfix', 'closed'),
            'ALL': _status_map.values(),
        }

        def _finalize(self, **kw):
            if not self.params or self.params.keys() == {'sort'}:
                raise BiteError('no supported search terms or options specified')

            query = self.params.get('q', {})

            # default to showing issues that aren't closed
            if 'status' not in query:
                open_status_query = ' OR '.join(
                    f'state = "{x}"' for x in self._status_aliases['OPEN'])
                query['status'] = f'({open_status_query})'

            self.params['q'] = ' AND '.join(query.values())

            # default to sorting ascending by issue ID
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
            self.params.setdefault('q', {})['summary'] = f"{' AND '.join(or_queries)}"
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
            self.params[k] = f'{inverse}{order_var}'
            self.options.append(f"Sort order: {v}")

        def status(self, k, v):
            or_terms = []
            for status in v:
                try:
                    or_terms.append(self._status_map[status])
                except KeyError:
                    try:
                        or_terms.extend(self._status_aliases[status])
                    except KeyError:
                        choices = ', '.join(sorted(self._status_map.keys()))
                        aliases = ', '.join(sorted(self._status_aliases.keys()))
                        raise BiteError(
                            f'invalid status: {status!r} '
                            f'(available choices: {choices}) '
                            f'(aliases: {aliases})')
            q_str = ' OR '.join(f'state = "{x}"' for x in or_terms)
            if len(or_terms) > 1:
                q_str = f"({q_str})"
            self.params.setdefault('q', {})[k] = q_str
            self.options.append(f"Status: {' OR '.join(or_terms)}")

        def priority(self, k, v):
            or_terms = []
            for priority in v:
                try:
                    or_terms.append(self._priority_map[priority])
                except KeyError:
                    choices = ', '.join(sorted(self._priority_map.keys()))
                    raise BiteError(
                        f'invalid priority: {priority!r} (available choices: {choices})')
            q_str = ' OR '.join(f'priority = "{x}"' for x in or_terms)
            if len(or_terms) > 1:
                q_str = f"({q_str})"
            self.params.setdefault('q', {})[k] = q_str
            self.options.append(f"Priority: {' OR '.join(or_terms)}")

        def type(self, k, v):
            or_terms = []
            for type in v:
                try:
                    or_terms.append(self._type_map[type])
                except KeyError:
                    choices = ', '.join(sorted(self._type_map.keys()))
                    raise BiteError(
                        f'invalid type: {type!r} (available choices: {choices})')
            q_str = ' OR '.join(f'kind = "{x}"' for x in or_terms)
            if len(or_terms) > 1:
                q_str = f"({q_str})"
            self.params.setdefault('q', {})[k] = q_str
            self.options.append(f"Type: {' OR '.join(or_terms)}")

        @alias('modified')
        def created(self, k, v):
            self.params.setdefault('q', {})[k] = f'{self.remap[k]} >= {v.isoformat()}'
            self.options.append(f'{k.capitalize()}: {v} (since {v.isoformat()})')

        @alias('watchers')
        def votes(self, k, v):
            self.params.setdefault('q', {})[k] = f'{self.remap.get(k, k)} >= {v}'
            self.options.append(f'{k.capitalize()}: >= {v}')

        def id(self, k, v):
            q_str = ' OR '.join(f'id = {x}' for x in v)
            if len(v) > 1:
                q_str = f"({q_str})"
            self.params.setdefault('q', {})[k] = q_str
            self.options.append(f"IDs: {', '.join(map(str, v))}")


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
        for issue in data:
            yield self.service.item(self.service, issue, get_desc=self._get_desc)


@req_cmd(Bitbucket, cmd='comments')
class _CommentsRequest(BaseCommentsRequest):
    """Construct a comments request."""

    def __init__(self, **kw):
        super().__init__(**kw)

        if self.ids is None:
            raise ValueError(f'No {self.service.item.type} ID(s) specified')
        self.options.append(f"IDs: {', '.join(self.ids)}")

        reqs = []
        for i in self.ids:
            reqs.append(BitbucketPagedRequest(
                service=self.service, endpoint=f'/issues/{i}/comments'))

        self._reqs = tuple(reqs)

    def parse(self, data):
        def items():
            # skip comments that have no content, i.e. issue attribute changes
            for i, comments in zip(self.ids, data):
                comments = comments['values']
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
        yield from self.filter(items())


@req_cmd(Bitbucket, cmd='attachments')
class _AttachmentsRequest(Request):
    """Construct an attachments request."""

    def __init__(self, ids=(), attachment_ids=(), get_data=False, **kw):
        super().__init__(**kw)
        if not any((ids, attachment_ids)):
            raise ValueError(f'No ID(s) specified')

        if attachment_ids:
            ids = list(x[0] for x in attachment_ids)

        reqs = []
        for i in ids:
            reqs.append(BitbucketPagedRequest(
                service=self.service, endpoint=f'/issues/{i}/attachments'))

        self.ids = ids
        self.attachment_ids = attachment_ids
        self._reqs = tuple(reqs)
        self._get_data = get_data

    def parse(self, data):
        for attachments in data:
            if self.ids:
                attachments = attachments['values']

            if self._get_data:
                a_names = set()
                reqs = []
                for i, a_ids in self.attachment_ids:
                    if not a_ids:
                        a_ids = [x['name'] for x in attachments]
                    a_names.update(a_ids)
                    for a_id in a_ids:
                        reqs.append(RESTRequest(
                            service=self.service, raw=True,
                            endpoint=f'/issues/{i}/attachments/{a_id}'))
                try:
                    content = tuple(Request(
                        service=self.service, reqs=reqs, raw=True).send(allow_redirects=True))
                except BitbucketError as e:
                    if e.code == 404 and e.orig_msg in a_names:
                        raise BitbucketError(f'unknown attachment: {e.orig_msg!r}')
                    raise
            else:
                content = self._none_gen

            yield tuple(
                self.service.attachment(
                    data=c, filename=a['name'], url=a['links']['self']['href'])
                for a, c in zip(attachments, content))


@req_cmd(Bitbucket, cmd='changes')
class _ChangesRequest(BaseChangesRequest):
    """Construct a changes request."""

    def __init__(self, **kw):
        super().__init__(**kw)

        if self.ids is None:
            raise ValueError(f'No {self.service.item.type} ID(s) specified')
        self.options.append(f"IDs: {', '.join(self.ids)}")

        reqs = []
        for i in self.ids:
            reqs.append(BitbucketPagedRequest(
                service=self.service, endpoint=f'/issues/{i}/changes'))

        self._reqs = tuple(reqs)

    def parse(self, data):
        def items():
            for changes in data:
                changes = changes['values']
                yield tuple(BitbucketEvent(
                    self.service, id=c['id'], count=j+1, change=c)
                    for j, c in enumerate(changes))
        yield from self.filter(items())


@req_cmd(Bitbucket, cmd='get')
class _GetRequest(BaseGetRequest):
    """Construct requests to retrieve all known data for given issue IDs."""

    def __init__(self, get_comments=True, **kw):
        super().__init__(get_comments=get_comments, **kw)
        self._get_comments = get_comments

    def parse(self, data):
        items, comments, attachments, changes = data
        for item in items:
            # Prepend comment for description which is provided by
            # GetItemRequest instead of CommentsRequest.
            if self._get_comments:
                item.comments = (item.description,) + next(comments)
            else:
                item.comments = next(comments)
            item.attachments = next(attachments)
            item.changes = next(changes)
            yield item
