"""Web scraper for Trac without RPC support."""

import lxml.html
from urllib.parse import urlparse, parse_qs

from dateutil.parser import parse as parsetime
from snakeoil.demandload import demandload
from snakeoil.klass import aliased, alias

from . import TracTicket, TracComment, TracAttachment, TracEvent, BaseSearchRequest
from .. import Service
from .._csv import CSVRequest
from .._html import HTML
from .._reqs import (
    req_cmd, Request, NullRequest, URLRequest,
    BaseCommentsRequest, BaseChangesRequest,
)
from .._xml import XMLRequest
from ...cache import Cache
from ...exceptions import BiteError, ParsingError
from ...utc import utc

demandload(
    'snakeoil.strings:pluralism',
    'bite.service.trac:jsonrpc',
)


class TracScraperCache(Cache):

    def __init__(self, **kw):
        # Default columns to enable for search mode, as taken from Trac's
        # tracker, renamed using the service's attribute aliases.
        defaults = {
            'search_cols': (
                'id', 'summary', 'status', 'priority', 'owner', 'type', 'milestone',
                'component', 'version', 'severity', 'resolution', 'created', 'modified',
                'reporter', 'keywords', 'cc', 'description',
            )
        }

        super().__init__(defaults=defaults, **kw)


class TracScraperTicket(TracTicket):

    def __init__(self, **kw):
        # Convert datetime strings to objects, created/modifed fields come
        # from CSV dumps when scraping.
        for attr in ('time', 'changetime', 'created', 'modified'):
            v = kw.pop(attr, None)
            if v is not None:
                v = parsetime(v)
                if v.tzinfo is None:
                    v = v.replace(tzinfo=utc)
                setattr(self, attr, v)

        super().__init__(**kw)


class _TracScraperXMLItem(object):
    """RSS event feed items."""

    _xml_namespace = {'dc': "http://purl.org/dc/elements/1.1/"}

    def __init__(self, el):
        self._el = el

    @property
    def title(self):
        return self._el.xpath('./title/text()')

    @property
    def creator(self):
        # extract comment creator
        try:
            creator = self._el.xpath('./dc:creator/text()', namespaces=self._xml_namespace)[0]
        except IndexError:
            try:
                creator = self._el.xpath('./author/text()')[0]
            except IndexError:
                creator = None
        return creator

    @property
    def desc(self):
        return lxml.html.fromstring(self._el.xpath('./description/text()')[0])

    @property
    def created(self):
        return parsetime(self._el.xpath('./pubDate/text()')[0])

    @classmethod
    def parse(cls, tree):
        for item in tree.xpath('//item'):
            yield cls(item)


class TracScraperRSSComment(TracComment):

    @classmethod
    def parse(cls, data):
        for id, tree in data:
            count = 1
            l = []
            for item in _TracScraperXMLItem.parse(tree):
                # skip attachment events
                if item.title and item.title[0] == 'attachment set':
                    continue

                text = '\n'.join(x.text_content().strip() for x in item.desc.xpath('//p'))
                # skip events without any comment
                if not text:
                    continue

                l.append(cls(
                    count=count, creator=item.creator, created=item.created, text=text))
                count += 1
            yield tuple(l)


class TracScraperRSSAttachment(TracAttachment):

    _xml_namespace = {'dc': "http://purl.org/dc/elements/1.1/"}

    @classmethod
    def parse(cls, data):
        for id, tree in data:
            l = []
            for item in _TracScraperXMLItem.parse(tree):
                # skip non-attachment events
                if not item.title or item.title[0] != 'attachment set':
                    continue

                filename = item.desc.xpath('//em')[0].text_content()
                l.append(cls(
                    creator=item.creator, created=item.created, filename=filename))
            yield tuple(l)


class TracScraperRSSEvent(TracEvent):

    _xml_namespace = {'dc': "http://purl.org/dc/elements/1.1/"}

    @classmethod
    def parse(cls, data):
        for id, tree in data:
            l = []
            count = 1
            for item in _TracScraperXMLItem.parse(tree):
                # skip comments and attachment events
                if not item.title or item.title[0] == 'attachment set':
                    continue

                changes = {}

                # change elements are found in the first unordered list inside
                # the description
                events = item.desc.xpath('//ul[1]//li')
                for change in events:
                    field = change.xpath('./strong/text()')[0]
                    updates = change.xpath('./em/text()')
                    if updates:
                        removed = added = None
                        if len(updates) == 2:
                            removed, added = updates
                        elif len(updates) == 1:
                            li_text = ''.join(change.xpath('./text()')).strip()
                            value = change.xpath('./em/text()')[0]
                            if li_text in ('deleted', 'removed'):
                                removed = value
                            elif li_text in ('set to', 'added'):
                                added = value
                            else:
                                raise ParsingError(
                                    f'item {id}: change {count}: '
                                    f'unknown change action: {li_text}')
                        changes[field] = (removed, added)
                    else:
                        # change fields without regular textual actions
                        # descriptions, e.g. updating the ticket description
                        changes[field] = 'modified'

                l.append(cls(
                    count=count, creator=item.creator, created=item.created, changes=changes))
                count += 1
            yield tuple(l)


class _BaseTracScraper(Service):
    """Base service supporting the Trac-based ticket trackers."""

    _cache_cls = TracScraperCache

    item = TracScraperTicket
    item_endpoint = '/ticket/{id}'
    attachment = TracAttachment
    attachment_endpoint = '/ticket/{id}/{filename}'

    def __init__(self, max_results=None, **kw):
        # Trac uses a setting of 0 to disable paging search results.
        if max_results is None:
            max_results = 0
        # store kwargs to morph classes on login
        self._init_kw = kw
        super().__init__(max_results=max_results, **kw)

    def _morph(self):
        """Morph to a JSON-RPC based service."""
        return jsonrpc.TracJsonrpc(**self._init_kw)

class TracScraper(_BaseTracScraper, HTML):
    """Service supporting scraping Trac-based ticket trackers."""

    _service = 'trac-scraper'


class TracScraperCSV(_BaseTracScraper):
    """Service supporting pulling CSV/RSS data from Trac-based ticket trackers."""

    _service = 'trac-scraper-csv'


@req_cmd(TracScraper, name='SearchRequest', cmd='search')
class _SearchRequest(BaseSearchRequest, URLRequest):
    """Construct a web search request."""

    # map from standardized kwargs name to expected service parameter name
    BaseSearchRequest._params_map.update({
        'fields': 'col',
    })

    def __init__(self, get_desc=False, **kw):
        self._get_desc = get_desc
        super().__init__(endpoint='/query', **kw)

    def parse(self, data):
        """Parsing function for the raw HTML pages."""
        try:
            table = data.xpath('//table[@class="listing tickets"]')[0]
        except IndexError:
            # no issues exist
            return ()
        for row in table.xpath('./tbody/tr'):
            cols = row.xpath('./td')
            # no issues exist
            if len(cols) <= 1:
                break
            d = {}
            for c in cols:
                k = c.get('class')
                try:
                    a = c.xpath('./a')[0]
                    if k.endswith('time'):
                        v = parsetime(
                            parse_qs(urlparse(next(a.iterlinks())[2])[4])['from'][0])
                    else:
                        v = a.text
                except IndexError:
                    v = c.text.strip()
                # strip number symbol from IDs if it exists
                if k == 'id' and v[0] == '#':
                    v = v[1:]
                d[k] = v
            yield self.service.item(get_desc=self._get_desc, **d)

    @aliased
    class ParamParser(BaseSearchRequest.ParamParser):

        def _finalize(self, **kw):
            super()._finalize()

            # limit requested fields by default
            self.params.setdefault('fields', ('id', 'owner', 'summary'))

        def terms(self, k, v):
            or_queries = []
            display_terms = []
            for term in v:
                or_terms = [x.replace('"', '\\"') for x in term.split(',')]
                or_display_terms = [f'"{x}"' for x in or_terms]
                if len(or_terms) > 1:
                    or_queries.extend(or_terms)
                    display_terms.append(f"({' OR '.join(or_display_terms)})")
                else:
                    or_queries.append(or_terms[0])
                    display_terms.append(or_display_terms[0])
            # space-separated AND queries are only supported in 1.2.1 onwards
            # https://trac.edgewall.org/ticket/10152
            self.params['summary'] = [f"~{x}" for x in or_terms]
            self.options.append(f"Summary: {' AND '.join(display_terms)}")

        def fields(self, k, v):
            # TODO: support field aliases?
            unknown_fields = set(v).difference(self.service.cache['search_cols'])
            if unknown_fields:
                raise BiteError(
                    f"unknown field{pluralism(unknown_fields)}: {', '.join(unknown_fields)}\n"
                    f"available fields: {', '.join(self.service.cache['search_cols'])}")
            self.params[k] = [self.service.item.attribute_aliases.get(x, x) for x in v]
            self.options.append(f"{k.capitalize()}: {' '.join(v)}")

        @alias('reporter')
        def owner(self, k, v):
            self.params[k] = [f"~{x}" for x in v]
            self.options.append(f"{self.service.item.attributes[k]}: {', '.join(v)}")


@req_cmd(TracScraperCSV, name='SearchRequest', cmd='search')
class _SearchRequestCSV(CSVRequest, _SearchRequest):
    """Construct a search request pulling the CSV format."""

    def __init__(self, **kw):
        super().__init__(**kw)
        self.params['format'] = 'csv'

    def parse(self, data):
        for item in data:
            yield self.service.item(get_desc=self._get_desc, **item)


@req_cmd(TracScraperCSV)
class _GetItemRequest(_SearchRequestCSV):
    """Construct an item request."""

    def __init__(self, service, ids, **kw):
        if ids is None:
            raise ValueError(f'No {service.item.type} ID(s) specified')
        # request all fields by default
        kw.setdefault('fields', service.cache['search_cols'])
        super().__init__(service=service, id=ids, status=['ALL'], get_desc=True, **kw)

        self.ids = ids

    def parse(self, data):
        yield from super().parse(data)


@req_cmd(TracScraperCSV, name='_ChangelogRequest')
class _ChangelogRequest(Request):
    """Construct a changelog request pulling the RSS comments feed."""

    _xml_namespace = {'dc': "http://purl.org/dc/elements/1.1/"}

    def __init__(self, ids=None, data=None, **kw):
        super().__init__(**kw)
        if ids is None and data is None:
            raise ValueError(f'No {self.service.item.type} ID(s) specified')

        if data is None:
            reqs = []
            for i in ids:
                reqs.append(XMLRequest(
                    service=self.service, endpoint=f'/ticket/{i}?format=rss'))
        else:
            reqs = [NullRequest()]

        self._reqs = tuple(reqs)
        self.ids = ids
        self._data = data

    def parse(self, data):
        # TODO: Fallback to raw HTML parsing for sites that disable the RSS
        # feed support, e.g. pidgin.
        if self._data is not None:
            yield from self._data
        else:
            yield from data


@req_cmd(TracScraperCSV, cmd='comments')
class _CommentsRequest(BaseCommentsRequest, _ChangelogRequest):
    """Construct a comments request."""

    def __init__(self, **kw):
        super().__init__(**kw)

        if self.ids is None:
            raise ValueError(f'No {self.service.item.type} ID(s) specified')
        self.options.append(f"IDs: {', '.join(self.ids)}")

    def parse(self, data):
        data = super().parse(data)
        yield from self.filter(TracScraperRSSComment.parse(zip(self.ids, data)))


@req_cmd(TracScraperCSV, cmd='attachments')
class _AttachmentsRequest(_ChangelogRequest):
    """Construct an attachments request."""

    def parse(self, data):
        data = super().parse(data)
        yield from TracScraperRSSAttachment.parse(zip(self.ids, data))


@req_cmd(TracScraperCSV, cmd='changes')
class _ChangesRequest(BaseChangesRequest, _ChangelogRequest):
    """Construct a changes request."""

    def __init__(self, **kw):
        super().__init__(**kw)

        if self.ids is None:
            raise ValueError(f'No {self.service.item.type} ID(s) specified')
        self.options.append(f"IDs: {', '.join(self.ids)}")

    def parse(self, data):
        data = super().parse(data)
        yield from self.filter(TracScraperRSSEvent.parse(zip(self.ids, data)))


@req_cmd(TracScraperCSV, cmd='get')
class _GetRequest(Request):
    """Construct requests to retrieve all known data for given issue IDs."""

    def __init__(self, service, ids, get_comments=True, get_attachments=True, get_changes=False, **kw):
        super().__init__(service=service, **kw)
        if not ids:
            raise ValueError('No {self.service.item.type} ID(s) specified')

        reqs = [self.service.GetItemRequest(ids=ids, **kw)]
        if any((get_comments, get_attachments, get_changes)):
            reqs.append(self.service._ChangelogRequest(ids=ids))

        self.ids = ids
        self._reqs = tuple(reqs)
        self._get_comments = get_comments
        self._get_attachments = get_attachments
        self._get_changes = get_changes

    def parse(self, data):
        data = super().parse(data)
        items = tuple(next(data))

        comments = self._none_gen
        attachments = self._none_gen
        changes = self._none_gen

        if any((self._get_comments, self._get_attachments, self._get_changes)):
            changelogs = tuple(next(data))
            if self._get_comments:
                item_descs = ((x.description,) for x in items)
                item_comments = self.service.comments(ids=self.ids, data=changelogs)
                comments = (x + y for x, y in zip(item_descs, item_comments))
            if self._get_attachments:
                attachments = self.service.attachments(ids=self.ids, data=changelogs)
            if self._get_changes:
                changes = self.service.changes(ids=self.ids, data=changelogs)

        for item in items:
            item.comments = next(comments)
            item.attachments = next(attachments)
            item.changes = next(changes)
            yield item
