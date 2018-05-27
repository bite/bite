"""Web scraper for Trac without RPC support."""

import csv
import io
from urllib.parse import urlparse, parse_qs

from dateutil.parser import parse as parsetime
from snakeoil.klass import aliased, alias
from snakeoil.strings import pluralism

from . import TracTicket, TracAttachment
from .._html import HTML
from .._rest import REST, RESTRequest
from .._reqs import ParseRequest, req_cmd
from ...cache import Cache
from ...exceptions import BiteError


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


class TracScraper(HTML, REST):
    """Service supporting the Trac-based ticket trackers."""

    _service = 'trac-scraper'
    _cache_cls = TracScraperCache

    item = TracTicket
    item_endpoint = '/ticket/{id}'
    attachment = TracAttachment

    def __init__(self, max_results=None, **kw):
        # unsure if there is a sane upper limit on the max items per page, but we'll use 250
        if max_results is None:
            max_results = 250
        super().__init__(max_results=max_results, **kw)


class _SearchRequest(ParseRequest, RESTRequest):
    """Construct a search request.

    Query docs:
        https://trac.edgewall.org/wiki/TracQuery
    """

    # map from standardized kwargs name to expected service parameter name
    _params_map = {
        'created': 'time',
        'modified': 'changetime',
        'sort': 'order',
    }

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
    class ParamParser(ParseRequest.ParamParser):

        # Map of allowed sorting input values to service parameters.
        _sorting_map = {
            'assignee': 'owner',
            'id': 'id',
            'created': 'created',
            'modified': 'modified',
            'status': 'status',
            'description': 'description',
            'creator': 'reporter',
            'milestone': 'milestone',
            'component': 'component',
            'summary': 'summary',
            'priority': 'priority',
            'keywords': 'keywords',
            'version': 'version',
            'platform': 'platform',
            'difficulty': 'difficulty',
            'type': 'type',
            'wip': 'wip',
            'severity': 'severity',
        }

        # map of status alias names to matching query values
        _status_aliases = {
            'OPEN': '!closed',
            'CLOSED': 'closed',
            'ALL': '!*',
        }

        def _finalize(self, **kw):
            # default to sorting ascending by ID
            sort = self.params.pop('sort', {'order': 'id'})

            if not self.params:
                raise BiteError('no supported search terms or options specified')

            # disable results paging
            self.params['max'] = self.service.max_results

            # default to sorting ascending by ID
            self.params.update(sort)

            # limit requested fields by default
            fields = self.params.get('fields', ('id', 'owner', 'summary'))
            self.params['col'] = fields

            # default to returning only open tickets
            if 'status' not in self.params:
                self.params['status'] = '!closed'

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

        def status(self, k, v):
            # TODO: cache and check available status values for configured services
            self.params[k] = [self._status_aliases.get(x, x) for x in v]
            self.options.append(f"{k.capitalize()}: {', '.join(v)}")

        @alias('modified')
        def created(self, k, v):
            self.params[k] = f'{v.isoformat()}..'
            self.options.append(f'{k.capitalize()}: {v} (since {v.isoformat()})')

        def sort(self, k, v):
            if v[0] == '-':
                key = v[1:]
                desc = 1
            else:
                key = v
                desc = 0
            try:
                order_var = self._sorting_map[key]
            except KeyError:
                choices = ', '.join(sorted(self._sorting_map.keys()))
                raise BiteError(
                    f'unable to sort by: {key!r} (available choices: {choices}')
            d = {'order': order_var}
            if desc:
                d['desc'] = desc
            self.params[k] = d
            self.options.append(f"Sort order: {v}")

        @alias('reporter')
        def owner(self, k, v):
            self.params[k] = '|'.join(v)
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
