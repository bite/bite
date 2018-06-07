"""Web scraper for Trac without RPC support."""

from itertools import chain
from urllib.parse import urlparse, parse_qs

from dateutil.parser import parse as parsetime
from snakeoil.demandload import demandload
from snakeoil.klass import aliased, alias

from . import TracTicket, TracAttachment, BaseSearchRequest
from .. import Service
from .._csv import CSVRequest
from .._html import HTML
from .._reqs import req_cmd, Request, NullRequest, URLRequest
from ...cache import Cache
from ...exceptions import BiteError

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


class _BaseTracScraper(Service):
    """Base service supporting the Trac-based ticket trackers."""

    _cache_cls = TracScraperCache

    item = TracTicket
    item_endpoint = '/ticket/{id}'
    attachment = TracAttachment

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
            yield self.service.item(self.service, get_desc=self._get_desc, **d)

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
            yield self.service.item(self.service, get_desc=self._get_desc, **item)


@req_cmd(TracScraperCSV)
class _GetItemRequest(_SearchRequestCSV):
    """Construct an item request."""

    def __init__(self, service, ids, **kw):
        if ids is None:
            raise ValueError(f'No {service.item.type} ID(s) specified')
        # request all fields by default
        kw.setdefault('fields', service.cache['search_cols'])
        super().__init__(service=service, id=ids, get_desc=True, **kw)

        self.ids = ids

    def parse(self, data):
        yield from super().parse(data)


@req_cmd(TracScraperCSV, cmd='get')
class _GetRequest(_GetItemRequest):
    """Construct requests to retrieve all known data for given issue IDs."""

    def __init__(self, get_comments=True, get_attachments=True, get_changes=False, **kw):
        super().__init__(**kw)

        self._get_comments = get_comments
        self._get_attachments = get_attachments
        self._get_changes = get_changes

    def parse(self, data):
        items = super().parse(data)
        for item in items:
            yield item
