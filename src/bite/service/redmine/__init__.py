"""Support Redmine's REST interface.

API docs:
    - https://www.redmine.org/projects/redmine/wiki/Rest_api
"""

from itertools import chain

from dateutil.parser import parse as dateparse
from snakeoil.klass import aliased, alias

from .._reqs import (
    OffsetPagedRequest, Request, req_cmd,
    BaseCommentsRequest, QueryParseRequest,
)
from .._rest import REST, RESTRequest
from ...exceptions import BiteError, RequestError
from ...objects import Item, Comment, Attachment, Change, TimeInterval


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
        'closed': 'closed_on',
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
        ('category', 'Category'),
    )

    type = 'issue'

    def __init__(self, service, get_desc=False, **kw):
        # TODO: clean up item initialization
        # initialize fields that can be blank so the service won't return them
        self.closed_on = None
        self.assigned_to = None
        self.category = None

        for k, v in kw.items():
            # strip "Bug #ID (status): " prefix from titles
            if k == 'title':
                v = v.partition(': ')[2]
            elif k in ('created_on', 'updated_on', 'closed_on',):
                v = dateparse(v)
            elif k in ('author', 'assigned_to', 'status', 'priority', 'category'):
                v = v['name']

            if k == 'custom_fields':
                for field in v:
                    # allow fields without specified values
                    setattr(self, field['name'], field.get('value'))
            else:
                setattr(self, k, v)

        description = getattr(self, 'description', None)
        if get_desc and description:
            self.description = RedmineComment(
                count=0, creator=self.author, created=self.created_on, text=description.strip())


class RedmineComment(Comment):
    pass


class RedmineAttachment(Attachment):
    pass


class RedmineEvent(Change):
    pass


class Redmine(REST):
    """Service supporting the Redmine-based issue trackers."""

    _service_error_cls = RedmineError

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


# TODO: toss this when upstream stops supporting it
class Redmine3_2(Redmine):
    """Service supporting Redmine 3.2 issue trackers."""


class RedmineElastic(Redmine):
    """Service supporting the Redmine-based issue trackers with elasticsearch plugin."""


class RedminePagedRequest(OffsetPagedRequest, RESTRequest):

    _offset_key = 'offset'
    _size_key = 'limit'
    _total_key = 'total_count'


@req_cmd(Redmine)
class _GetItemRequest(QueryParseRequest, RedminePagedRequest):
    """Construct an issue request."""

    def __init__(self, *, service, ids=None, searchreq=False, get_desc=True,
                 sliced=False, **kw):
        self._ids = list(map(str, ids)) if ids is not None else ids
        if self._ids is not None:
            kw['ids'] = self._ids
        # running as a search request filter
        self._searchreq = searchreq
        self._get_desc = get_desc
        self._sliced = sliced
        super().__init__(service=service, endpoint=f'/issues.{service._ext}', **kw)

    def send(self, **kw):
        # Slice request into pieces if it gets too long otherwise we get
        # HTTP 500s due to URL length. Note that this means sorting won't
        # work for large queries.
        if self._ids and len(self._ids) > 100:
            ids = list(self._ids)
            reqs = []
            while ids:
                req = self.__class__(service=self.service, get_desc=self._get_desc, sliced=True)
                req.params = dict(self.params)
                req.params['issue_id'] = ','.join(ids[:100])
                reqs.append(req)
                ids = ids[100:]
            combined_req = Request(service=self.service, reqs=reqs)
            items = chain.from_iterable(combined_req.send(**kw))
        else:
            items = super().send(**kw)

        return items

    def parse(self, data):
        issues = data['issues']
        for issue in issues:
            yield self.service.item(self.service, get_desc=self._get_desc, **issue)

    @aliased
    class ParamParser(QueryParseRequest.ParamParser):

        # Map of allowed sorting input values to service parameters determined by
        # looking at available values on the web interface.
        _sorting_map = {
            'status': 'status',
            'priority': 'priority',
            'title': 'subject',
            'id': 'id',
            'created': 'created_on',
            'modified': 'updated_on',
            'closed': 'closed_on',
            'assignee': 'assigned_to',
            'creator': 'author',
            'version': 'fixed_version',
            'category': 'category',
        }

        def _finalize(self, **kw):
            if not any((self.params, self.request._sliced, self.request._searchreq)):
                raise BiteError('no supported options specified')

            # return all non-closed issues by default
            if 'status_id' not in self.params:
                if self.request._searchreq:
                    self.params['status_id'] = 'open'
                else:
                    self.params['status_id'] = '*'

            # sort by ascending ID by default
            if 'sort' not in self.params:
                self.params['sort'] = 'id'

        def ids(self, k, v):
            id_strs = list(map(str, v))
            self.params['issue_id'] = ','.join(id_strs)
            self.options.append(f"IDs: {', '.join(id_strs)}")

        def sort(self, k, v):
            sorting_terms = []
            for sort in v:
                if sort[0] == '-':
                    key = sort[1:]
                    desc = ':desc'
                else:
                    key = sort
                    desc = ''
                try:
                    order_var = self._sorting_map[key]
                except KeyError:
                    choices = ', '.join(sorted(self._sorting_map.keys()))
                    raise BiteError(
                        f'unable to sort by: {key!r} (available choices: {choices}')
                sorting_terms.append(f'{order_var}{desc}')
            self.params[k] = ','.join(sorting_terms)
            self.options.append(f"Sort order: {', '.join(v)}")

        @alias('modified', 'closed')
        def created(self, k, v):
            if not isinstance(v, TimeInterval):
                v = TimeInterval(v)
            start, end = v
            if start and end:
                range_str = f'><{start.utcformat}|{end.utcformat}'
            elif start:
                range_str = f'>={start.utcformat}'
            else:
                range_str = f'<={end.utcformat}'
            field = self.service.item.attribute_aliases[k]
            self.params[field] = range_str
            self.options.append(f'{k.capitalize()}: {v}')

        def status(self, k, v):
            # TODO: map between statuses and their IDs here -- only the
            # aggregate values (open, closed, *) work unmapped
            self.params['status_id'] = v
            self.options.append(f"{k.capitalize()}: {v}")

        # TODO: requires cached service categories
        # def category(self, k, v):
            # self.params['category_id'] = self.service.cache.category[v]
            # self.options.append(f"{k.capitalize()}: {v}")

        def terms(self, k, v):
            # raw issue search doesn't support multiple terms
            term = ' '.join(v)
            self.params.add('f[]', 'subject')
            self.params['op[subject]'] = '~'
            self.params['v[subject][]'] = term
            self.options.append(f"Summary: {term}")


@req_cmd(Redmine3_2, name='GetItemRequest')
class _3_2GetItemRequest(_GetItemRequest):
    """Construct an issue request for Redmine 3.2.

    Older versions of Redmine don't seem to work with straight field parameter
    mappings. Instead the filter params generated when using the web interface
    are used.
    """

    @aliased
    class ParamParser(_GetItemRequest.ParamParser):

        # Map of allowed sorting input values to service parameters determined by
        # looking at available values on the web interface.
        _status_map = {
            'open': 'o',
            'closed': 'c',
            'all': '*',
        }

        def _finalize(self, **kw):
            if not self.request._ids:
                if not any((self.params, self.request._sliced)):
                    raise BiteError('no supported options specified')

                # return all non-closed issues by default
                if 'op[status_id]' not in self.params:
                    self.params.add('f[]', 'status_id')
                    if self.request._searchreq:
                        self.params['op[status_id]'] = 'o'
                    else:
                        self.params['op[status_id]'] = '*'

                # sort by ascending ID by default
                if 'sort' not in self.params:
                    self.params['sort'] = 'id'

        def status(self, k, v):
            # TODO: map between statuses and their IDs here -- only the
            # aggregate values (open, closed, *) work unmapped
            self.params.add('f[]', 'status_id')
            try:
                self.params['op[status_id]'] = self._status_map[v]
            except KeyError:
                raise BiteError(f'unknown status value: {v!r}')
            self.options.append(f"Status: {v}")

        @alias('modified', 'closed')
        def created(self, k, v):
            if not isinstance(v, TimeInterval):
                v = TimeInterval(v)
            start, end = v
            if start and end:
                op = '><'
                values = [start.utcformat, end.utcformat]
            elif start:
                op = '>='
                values = [start.utcformat]
            else:
                op = '<='
                values = [end.utcformat]
            field = self.service.item.attribute_aliases[k]
            self.params.add('f[]', field)
            self.params[f'op[{field}]'] = op
            for x in values:
                self.params.add(f'v[{field}][]', x)
            self.options.append(f'{k.capitalize()}: {v}')

        def ids(self, k, v):
            # Old redmine versions can't handle issue_id param requests so ignore it.
            pass


@req_cmd(Redmine)
class _CommentsRequest(BaseCommentsRequest):
    """Construct a comments request."""

    def __init__(self, **kw):
        super().__init__(**kw)

        if self.ids is None:
            raise ValueError(f'No {self.service.item.type} ID(s) specified')
        self.options.append(f"IDs: {', '.join(self.ids)}")

        reqs = []
        for i in self.ids:
            reqs.append(RESTRequest(
                service=self.service,
                endpoint=f'{self.service.webbase}/issues/{i}.{self.service._ext}?include=journals'))

        self._reqs = tuple(reqs)

    def parse(self, data):
        def items():
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
        yield from self.filter(items())


@req_cmd(Redmine, cmd='get')
class _GetRequest(_GetItemRequest):
    """Construct requests to retrieve all known data for given issue IDs."""

    def __init__(self, ids, get_comments=True, get_attachments=True, get_changes=False, **kw):
        super().__init__(ids=ids, **kw)
        if not ids:
            raise ValueError(f'No {self.service.item.type} ID(s) specified')
        self.ids = ids
        self._get_comments = get_comments
        self._get_attachments = get_attachments
        self._get_changes = get_changes

    def parse(self, data):
        items = list(super().parse(data))
        return self.yield_items(items)

    def yield_items(self, items):
        comments = self._none_gen
        attachments = self._none_gen
        changes = self._none_gen

        if any((self._get_comments, self._get_attachments, self._get_changes)):
            if self._get_comments:
                item_descs = ((x.description,) if getattr(x, 'description', False) else () for x in items)
                item_comments = self.service.CommentsRequest(ids=self.ids).send()
                comments = (x + y for x, y in zip(item_descs, item_comments))

        for item in items:
            item.comments = next(comments)
            item.attachments = next(attachments)
            item.changes = next(changes)
            yield item


@req_cmd(Redmine3_2, name='GetRequest', cmd='get')
class _3_2GetRequest(_3_2GetItemRequest, _GetRequest):
    """Construct requests to retrieve all known data for given issue IDs."""

    def __init__(self, **kw):
        super().__init__(**kw)

        reqs = []
        for i in self.ids:
            endpoint = f'{self.service.webbase}/issues/{i}.{self.service._ext}'
            reqs.append(RESTRequest(service=self.service, endpoint=endpoint))

        self._reqs = tuple(reqs)
        self._req = None

    def parse(self, data):
        items = list(
            self.service.item(self.service, get_desc=self._get_desc, **x['issue'])
            for x in data)
        return self.yield_items(items)


@req_cmd(Redmine3_2, name='SearchRequest', cmd='search')
class _BasicSearchRequest(_3_2GetItemRequest):
    """Construct a search request using the issues call.

    For older installs of redmine that don't support the search API.
    """

    def __init__(self, **kw):
        super().__init__(searchreq=True, **kw)


class _BaseSearchRequest(QueryParseRequest, RedminePagedRequest):

    def __init__(self, *, service, **kw):
        self._itemreq_extra_params = {}
        super().__init__(service=service, endpoint=f'/search.{service._ext}', **kw)
        self._itemreq = self.service.GetItemRequest(searchreq=True, **self.unused_params)
        self.options.extend(self._itemreq.options)

    def send(self):
        # only send search req if it actually has query params
        if self.params:
            issues = list(super().send())
        else:
            issues = []

        # query and pull additional issue fields not available via search
        if issues or self._itemreq.params:
            if issues:
                self._itemreq_extra_params['ids'] = issues
            self._itemreq.parse_params(**self._itemreq_extra_params)
            issues = self._itemreq.send()
        yield from issues

    def parse(self, data):
        # parse the search query results if a query exists
        issues = []
        if self.params:
            data = super().parse(data)
            issues = [x['id'] for x in data['results']]
        return issues


@req_cmd(Redmine, cmd='search')
class _SearchRequest(_BaseSearchRequest):
    """Construct a search request."""

    class ParamParser(QueryParseRequest.ParamParser):

        def _finalize(self, **kw):
            if self.query:
                self.params['q'] = ' AND '.join(self.query.values())

                # only return issues
                self.params['issues'] = 1

                # return all non-closed issues by default
                if 'status' not in self.request.unused_params:
                    self.params['open_issues'] = 1

                # only search titles by default
                self.params['titles_only'] = 1

        def terms(self, k, v):
            self.query['summary'] = '+'.join(v)
            self.options.append(f"Summary: {', '.join(map(str, v))}")


@req_cmd(RedmineElastic, name='SearchRequest', cmd='search')
class _ElasticSearchRequest(_BaseSearchRequest):
    """Construct an elasticsearch compatible search request.

    Assumes the elasticsearch plugin is installed:
        https://www.redmine.org/plugins/redmine_elasticsearch
        https://github.com/Restream/redmine_elasticsearch/wiki/Search-Quick-Reference
    """

    @aliased
    class ParamParser(QueryParseRequest.ParamParser):

        def _finalize(self, **kw):
            if not self.query:
                raise BiteError('no supported search terms or options specified')

            # return all non-closed issues by default
            if 'status' not in self.query:
                self.params['open_issues'] = 1

            q_str = ' AND '.join(self.query.values())
            self.params['q'] = f'_type:issue AND ({q_str})'

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
            self.query[k] = f"{k}:({' OR '.join(v)})"
            self.options.append(f"{k.capitalize()}: {', '.join(v)}")
            # make sure itemreq doesn't override our status
            self.request._itemreq_extra_params['status'] = '*'

        def category(self, k, v):
            self.query[k] = f"{k}:({' OR '.join(v)})"
            self.options.append(f"{k.capitalize()}: {', '.join(v)}")

        @alias('modified', 'closed')
        def created(self, k, v):
            if not isinstance(v, TimeInterval):
                v = TimeInterval(v)
            start, end = v
            if start and end:
                range_str = f'{start.isoformat()} TO {end.isoformat()}'
            elif start:
                range_str = f'{start.isoformat()} TO *'
            else:
                range_str = f'* TO {end.isoformat()}'
            field = self.service.item.attribute_aliases[k]
            self.query[k] = f'{field}:[{range_str}]'
            self.options.append(f'{k.capitalize()}: {v}')
