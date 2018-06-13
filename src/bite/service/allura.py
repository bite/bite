"""Support Allura's REST interface.

API docs:
    https://sourceforge.net/p/forge/documentation/API/
    https://sourceforge.net/p/forge/documentation/Allura%20API/
    https://forge-allura.apache.org/docs/getting_started/administration.html#public-api
"""

import html
import re

from dateutil.parser import parse as dateparse
from snakeoil.klass import aliased, alias

from ._jsonrest import JsonREST
from ._reqs import (
    NullRequest, Request, req_cmd,
    FlaggedPagedRequest, PagedRequest, URLParseRequest,
    BaseCommentsRequest, BaseChangesRequest,
)
from ._rest import RESTRequest
from ..exceptions import BiteError, RequestError
from ..objects import Item, Comment, Attachment, Change, TimeInterval
from ..utc import utc


class AlluraError(RequestError):
    """Allura service specific error."""

    def __init__(self, msg, code=None, text=None):
        msg = f'Allura error: {msg}'
        super().__init__(msg, code, text)


class AlluraTicket(Item):

    attributes = {
        'status': 'Status',
        'created_date': 'Created',
        'mod_date': 'Modified',
        'assigned_to': 'Assignee',
        'reported_by': 'Reporter',
        'summary': 'Title',
        'ticket_num': 'ID',
        'labels': 'Labels',
        'private': 'Private',
        'related_artifacts': 'Related',
    }

    attribute_aliases = {
        'created': 'created_date',
        'modified': 'mod_date',
        'owner': 'assigned_to',
        'creator': 'reported_by',
        'title': 'summary',
        'id': 'ticket_num',
    }

    _print_fields = (
        ('assigned_to', 'Assignee'),
        ('summary', 'Title'),
        ('ticket_num', 'ID'),
        ('status', 'Status'),
        ('labels', 'Labels'),
        ('created_date', 'Created'),
        ('mod_date', 'Modified'),
        ('related_artifacts', 'Related'),
        ('comments', 'Comments'),
        ('attachments', 'Attachments'),
        ('changes', 'Changes'),
    )

    # Defaults to ticket; however, projects can choose what they call it so
    # it's overridden per service instance.
    type = 'ticket'

    def __init__(self, service, get_desc=False, get_attachments=False, **kw):
        self.comments = None
        self.attachments = None
        self.changes = None

        for k in self.attributes.keys():
            v = kw.get(k)
            if k in ('created_date', 'mod_date') and v:
                # allura doesn't specify an offset for its timestamps, assume UTC
                v = dateparse(v).astimezone(utc)
            elif k == 'labels' and not v:
                v = None
            elif k == 'related_artifacts':
                if not v:
                    v = None
                else:
                    try:
                        v = tuple(x.rstrip('/').rsplit(f'/{service._tracker}/', 1)[1] for x in v)
                    except IndexError:
                        continue
            elif k == 'summary':
                v = html.unescape(v)
            setattr(self, k, v)

        # Store comment thread ID, note that search results don't include
        # discussion thread objects, so fall back to grabbing the value from the URL.
        if 'discussion_thread' in kw:
            self.thread_id = kw['discussion_thread']['_id']
        else:
            self.thread_id = kw['discussion_thread_url'].rstrip('/').rsplit('/', 1)[1]

        if get_desc:
            try:
                desc = html.unescape(kw['description'].strip())
            except KeyError:
                desc = ''
            self.description = AlluraComment(
                count=0, creator=self.reported_by, created=self.created_date, text=desc)

        if get_attachments:
            self.attachments = tuple(
                AlluraAttachment(
                    size=a['bytes'], url=a['url'], creator=self.reported_by,
                    created=self.created_date, filename=a['url'].rsplit('/', 1)[1])
                for a in kw['attachments'])


class AlluraComment(Comment):

    @classmethod
    def parse(cls, data):
        for posts in data:
            l = []
            for i, c in enumerate(posts, start=1):
                # Some trackers appear to have some crazy content with multiple
                # layers of html escaping, but we only undo one layer.
                text = html.unescape(c['text'].strip())
                # skip change events
                if not re.match(r'(- \*\*\w+\*\*: |- (Attachments|Description) has changed:\n\nDiff)', text):
                    l.append(cls(
                        count=i, creator=c['author'],
                        created=dateparse(c['timestamp']).astimezone(utc), text=text))
            yield tuple(l)


class AlluraAttachment(Attachment):

    @classmethod
    def parse(cls, data):
        for posts in data:
            l = []
            for p in posts:
                for a in p['attachments']:
                    l.append(cls(
                        creator=p['author'], created=dateparse(p['timestamp']).astimezone(utc),
                        size=a['bytes'], url=a['url'], filename=a['url'].rsplit('/', 1)[1]))
            yield tuple(l)


class AlluraEvent(Change):

    @classmethod
    def parse(cls, data):
        for posts in data:
            l = []
            for i, c in enumerate(posts, start=1):
                text = c['text'].strip()
                # find all attribute change events
                attr_changes = re.findall(r'- \*\*(\w+)\*\*: (.+)', text)
                # try to extract description changes
                field_changes = re.findall(
                    r'- (Description|Attachments) has changed:\n\n(Diff:\n\n~~~~(.*)~~~~)', text, re.DOTALL)
                if attr_changes or field_changes:
                    changes = {}
                    # don't show description changes if diff is empty
                    for field, diff, content in field_changes:
                        field = field.lower()
                        if content.strip():
                            changes[field] = f'\n{diff.strip()}'
                    for field, change in attr_changes:
                        field = field.lower()
                        key = AlluraTicket.attributes.get(field, field)
                        changed = change.split('-->')
                        if len(changed) == 2:
                            old = changed[0].strip()
                            new = changed[1].strip()
                            # skip empty change fields
                            if old or new:
                                changes[key] = (old, new)
                        else:
                            changes[key] = change
                    l.append(AlluraEvent(
                        count=i, creator=c['author'],
                        created=dateparse(c['timestamp']).astimezone(utc), changes=changes))
            yield tuple(l)


class Allura(JsonREST):
    """Service supporting the Allura trackers."""

    _service = 'allura'
    _service_error_cls = AlluraError

    item = AlluraTicket
    item_endpoint = '/{id}'

    def __init__(self, base, max_results=None, **kw):
        try:
            api_base, project = base.split('/p/', 1)
            project, tracker = project.strip('/').split('/', 1)
        except ValueError as e:
            raise BiteError(f'invalid project base: {base!r}')

        self._project = project
        self._tracker = tracker
        endpoint = f'/rest/p/{self._project}/{self._tracker}'

        # Allura allows projects to name/mount their ticket trackers under
        # any name (e.g. issues, bugs, tickets), try to determine the item name from this.
        self.item.type = self._tracker.rstrip('s')

        # 500 results appears to be the default maximum
        if max_results is None:
            max_results = 500
        super().__init__(
            endpoint=endpoint, base=api_base, max_results=max_results, **kw)
        self.webbase = base

    def inject_auth(self, request, params):
        raise NotImplementedError

    def parse_response(self, response):
        data = super().parse_response(response)
        if data.get('type') != 'error':
            return data
        else:
            self.handle_error(code=response.status_code, msg=data['error']['message'])


class AlluraPagedRequest(PagedRequest, RESTRequest):
    """Support navigating paged requests from Allura."""

    _page_key = 'page'
    _size_key = 'limit'
    _total_key = 'count'


class AlluraFlaggedPagedRequest(FlaggedPagedRequest, RESTRequest):
    """Support navigating paged requests from Allura."""

    _page_key = 'page'
    _size_key = 'limit'


@req_cmd(Allura, cmd='search')
class _SearchRequest(URLParseRequest, AlluraPagedRequest):
    """Construct a search request.

    Currently using on Solr on the backend, see the following docs for query help:
        https://lucene.apache.org/solr/guide/7_3/the-standard-query-parser.html
        http://www.solrtutorial.com/solr-query-syntax.html
        http://yonik.com/solr/
    """

    # map from standardized kwargs name to expected service parameter name
    _params_map = {
        'created': 'created_date',
        'modified': 'mod_date',
        'creator': 'reported_by',
        'assignee': 'assigned_to',
    }

    def __init__(self, **kw):
        super().__init__(endpoint='/search', **kw)

    def parse(self, data):
        data = super().parse(data)
        tickets = data['tickets']
        for ticket in tickets:
            yield self.service.item(self.service, **ticket)

    @aliased
    class ParamParser(URLParseRequest.ParamParser):

        # map of allowed sorting input values to service parameters
        _sorting_map = {
            'assignee': 'assigned_to_s',
            'id': 'ticket_num_i',
            'title': 'snippet_s',
            'description': 'text_s',
            'status': 'status_s',
            'created': 'created_date_dt',
            'modified': 'mod_date_dt',
            'creator': 'reported_by_s',
            'labels': 'labels_t',
            'votes': 'votes_total_i',
            'private': 'private_b',
            'muted': 'discussion_disabled_b',
            'milestone': '_milestone_s',
            'type': '_type_s',
            'needs': '_needs_s',
            'patch': '_patch_s',
        }

        def _finalize(self, **kw):
            if not self.params or self.params.keys() == {'sort'}:
                raise BiteError('no supported search terms or options specified')

            query = self.params.get('q', {})
            self.params['q'] = ' AND '.join(query.values())

            # default to sorting ascending by ID
            if 'sort' not in self.params:
                self.params['sort'] = 'ticket_num_i asc'

        def terms(self, k, v):
            or_queries = []
            display_terms = []
            for term in v:
                or_terms = [x.replace('"', '\\"') for x in term.split(',')]
                or_search_terms = [f'summary:"{x}"' for x in or_terms]
                or_display_terms = [f'"{x}"' for x in or_terms]
                if len(or_terms) > 1:
                    or_queries.append(f"({' OR '.join(or_search_terms)})")
                    display_terms.append(f"({' OR '.join(or_display_terms)})")
                else:
                    or_queries.append(or_search_terms[0])
                    display_terms.append(or_display_terms[0])
            self.params.setdefault('q', {})['summary'] = f"{' AND '.join(or_queries)}"
            self.options.append(f"Summary: {' AND '.join(display_terms)}")

        def id(self, k, v):
            id_str = None
            if len(v) > 1:
                first, last = v[0], v[-1]
                if v == list(range(first, last + 1)):
                    query_str = f"ticket_num:[{first} TO {last}]"
                    id_str = f'{first} - {last}'
                else:
                    or_terms = (f"ticket_num:{x}" for x in v)
                    query_str = f"({' OR '.join(or_terms)})"
            else:
                query_str = f"ticket_num:{v[0]}"
            self.params.setdefault('q', {})['id'] = query_str
            if id_str is None:
                id_str = ', '.join(map(str, v))
            self.options.append(f"{self.service.item.type.capitalize()} IDs: {id_str}")

        def sort(self, k, v):
            sorting_terms = []
            for sort in v:
                if sort[0] == '-':
                    key = sort[1:]
                    order = 'desc'
                else:
                    key = sort
                    order = 'asc'
                try:
                    order_var = self._sorting_map[key]
                except KeyError:
                    choices = ', '.join(sorted(self._sorting_map.keys()))
                    raise BiteError(
                        f'unable to sort by: {key!r} (available choices: {choices}')
                sorting_terms.append(f'{order_var} {order}')
            self.params[k] = ','.join(sorting_terms)
            self.options.append(f"Sort order: {', '.join(v)}")

        @alias('modified')
        def created(self, k, v):
            if not isinstance(v, TimeInterval):
                v = TimeInterval(v)
            start, end = v
            start = start.utcformat if start else '*'
            end = end.utcformat if end else '*'
            self.params.setdefault('q', {})[k] = f'{self.remap[k]}:[{start} TO {end}]'
            self.options.append(f'{k.capitalize()}: {v}')

        @alias('assignee')
        def creator(self, k, v):
            or_terms = [x.replace('"', '\\"') for x in v]
            or_search_terms = [f'{self.remap[k]}:"{x}"' for x in or_terms]
            or_display_terms = [f'"{x}"' for x in or_terms]
            self.params.setdefault('q', {})[k] = f"({' OR '.join(or_search_terms)})"
            self.options.append(f"{k.capitalize()}: {', '.join(or_display_terms)}")


@req_cmd(Allura)
class _GetItemRequest(Request):
    """Construct an issue request."""

    def __init__(self, ids, get_desc=True, get_attachments=True, **kw):
        super().__init__(**kw)
        if ids is None:
            raise ValueError(f'No {self.service.item.type} ID(s) specified')

        reqs = []
        for i in ids:
            reqs.append(RESTRequest(service=self.service, endpoint=f'/{i}'))

        self.ids = ids
        self._reqs = tuple(reqs)
        self._get_desc = get_desc
        self._get_attach = get_attachments

    def parse(self, data):
        for item in data:
            yield self.service.item(
                self.service, get_desc=self._get_desc, get_attachments=self._get_attach,
                **item['ticket'])


class _ThreadRequest(Request):
    """Construct a discussion thread request."""

    def __init__(self, ids=None, item_id=False, data=None, **kw):
        super().__init__(**kw)
        if ids is None:
            raise ValueError(f'No ID(s) specified')

        # pull thread IDs from items
        if item_id:
            self.service.client.progress_output('Determining message thread IDs')
            self.options.append(f"IDs: {', '.join(map(str, ids))}")
            items = self.service.SearchRequest(id=ids).send()
            ids = [x.thread_id for x in items]

        if data is None:
            reqs = []
            for i in ids:
                reqs.append(AlluraFlaggedPagedRequest(
                    service=self.service, endpoint=f'/_discuss/thread/{i}'))
        else:
            reqs = [NullRequest()]

        self.ids = ids
        self._reqs = tuple(reqs)
        self._data = data

    def parse(self, data):
        if self._data is not None:
            yield from self._data
        else:
            for item in data:
                posts = item['thread']['posts']
                yield posts
                if not posts:
                    self._exhausted = True


@req_cmd(Allura, cmd='comments')
class _CommentsRequest(BaseCommentsRequest, _ThreadRequest):
    """Construct a comments request."""

    def parse(self, data):
        thread_posts = super().parse(data)
        yield from self.filter(AlluraComment.parse(thread_posts))


@req_cmd(Allura, cmd='attachments')
class _AttachmentsRequest(_ThreadRequest):
    """Construct an attachments request."""

    def parse(self, data):
        thread_posts = super().parse(data)
        yield from AlluraAttachment.parse(thread_posts)


@req_cmd(Allura, cmd='changes')
class _ChangesRequest(BaseChangesRequest, _ThreadRequest):
    """Construct a changes request."""

    def parse(self, data):
        thread_posts = super().parse(data)
        yield from self.filter(AlluraEvent.parse(thread_posts))


@req_cmd(Allura, cmd='get')
class _GetRequest(_GetItemRequest):
    """Construct requests to retrieve all known data for given issue IDs."""

    def __init__(self, get_comments=True, get_attachments=True, get_changes=False, **kw):
        super().__init__(get_desc=get_comments, get_attachments=get_attachments, **kw)
        self._get_comments = get_comments
        self._get_attachments = get_attachments
        self._get_changes = get_changes

    def parse(self, data):
        items = list(super().parse(data))
        comments = self._none_gen
        attachments = self._none_gen
        changes = self._none_gen

        if any((self._get_comments, self._get_attachments, self._get_changes)):
            # request discussion thread data
            thread_ids = [x.thread_id for x in items]
            thread_req = _ThreadRequest(service=self.service, ids=thread_ids)
            threads = list(thread_req.send())
            if self._get_comments:
                item_descs = ((x.description,) for x in items)
                item_comments = self.service.CommentsRequest(
                    ids=thread_ids, data=threads).send()
                comments = (x + y for x, y in zip(item_descs, item_comments))
            if self._get_attachments:
                item_initial_attachments = (x.attachments for x in items)
                post_attachments = self.service.AttachmentsRequest(
                    ids=thread_ids, data=threads).send()
                attachments = (
                    x + y for x, y in zip(item_initial_attachments, post_attachments))
            if self._get_changes:
                changes = self.service.ChangesRequest(
                    ids=thread_ids, data=threads).send()

        for item in items:
            item.comments = next(comments)
            item.attachments = next(attachments)
            item.changes = next(changes)
            yield item

    def handle_exception(self, e):
        # TODO: move this to data iterator for various obj parsers
        if e.code == 404:
            raise RequestError('nonexistent item ID', code=e.code)
        raise e
