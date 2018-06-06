"""Web scraper for Trac without RPC support."""

import csv
import io
from urllib.parse import urlparse, parse_qs

from dateutil.parser import parse as parsetime
from snakeoil.demandload import demandload
from snakeoil.klass import aliased, alias

from . import TracTicket, TracAttachment, BaseSearchRequest
from .._html import HTMLRequest
from .._rest import REST, RESTRequest
from .._reqs import req_cmd
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


class TracScraper(REST):
    """Service supporting the Trac-based ticket trackers."""

    _service = 'trac-scraper'
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


class _SearchRequest(BaseSearchRequest, HTMLRequest):
    """Construct a web search request."""

    def __init__(self, **kw):
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
            yield self.service.item(self.service, get_desc=False, **d)

    @aliased
    class ParamParser(BaseSearchRequest.ParamParser):

        def _finalize(self, **kw):
            super()._finalize()

            # limit requested fields by default
            fields = self.params.get('fields', ('id', 'owner', 'summary'))
            self.params['col'] = fields

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


# Use the CSV format by default as it's faster than parsing the raw HTML pages.
@req_cmd(TracScraper, name='SearchRequest', cmd='search')
class _SearchRequestCSV(_SearchRequest):
    """Construct a search request pulling the CSV format."""

    def __init__(self, **kw):
        super().__init__(raw=True, **kw)
        self.params['format'] = 'csv'

    def parse(self, data):
        """Parsing function for the raw CSV content."""
        # Requesting the text content of the response doesn't remove the BOM so
        # we request the binary content and decode it ourselves to remove it.
        f = io.StringIO(data.decode('utf-8-sig'))
        headers = [x.lower() for x in f.readline().strip().split(',')]
        for item in csv.DictReader(f, fieldnames=headers):
            yield self.service.item(self.service, get_desc=False, **item)
