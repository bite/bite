"""Support Redmine's REST interface.

API docs:
    - http://www.redmine.org/projects/redmine/wiki/Rest_api
"""

from functools import partial

from .._reqs import OffsetPagedRequest, ParseRequest, req_cmd
from .._rest import REST, RESTRequest
from ...exceptions import BiteError, RequestError
from ...objects import Item


class RedmineError(RequestError):
    """Redmine service specific error."""

    def __init__(self, msg, code=None, text=None):
        msg = f'Redmine error: {msg}'
        super().__init__(msg, code, text)


class RedmineIssue(Item):

    attributes = {
    }

    attribute_aliases = {
        'title': 'summary',
    }

    _print_fields = (
        ('title', 'Title'),
        ('id', 'ID'),
        ('created', 'Reported'),
    )

    type = 'issue'

    def __init__(self, service, issue):
        for k, v in issue.items():
            # strip "Bug #ID (status): " prefix from titles
            if k == 'title':
                v = v.partition(': ')[2]
            setattr(self, k, v)


class Redmine(REST):
    """Service supporting the Redmine-based issue trackers."""

    item = RedmineIssue
    item_endpoint = '/issues/{id}'

    def __init__(self, max_results=None, **kw):
        # most redmine instances default to 100 results per query
        if max_results is None:
            max_results = 100
        super().__init__(max_results=max_results, **kw)

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


class _BaseSearchRequest(ParseRequest, RedminePagedRequest):
    """Construct a search request."""

    def __init__(self, *, service, **kw):
        super().__init__(service=service, endpoint=f'/search.{service._ext}', **kw)

    def parse(self, data):
        data = super().parse(data)
        issues = data['results']
        for issue in issues:
            yield self.service.item(self.service, issue)


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
class _ElasticSearchRequest(_BaseSearchRequest):
    """Construct an elasticsearch compatible search request.

    Assumes the elasticsearch plugin is installed:
        http://www.redmine.org/plugins/redmine_elasticsearch
        https://github.com/Restream/redmine_elasticsearch/wiki/Search-Quick-Reference
    """

    class ParamParser(ParseRequest.ParamParser):

        def __init__(self, **kw):
            super().__init__(**kw)
            self.query = {}

        def _finalize(self, **kw):
            if not self.query:
                raise BiteError('no supported search terms or options specified')

            # return all non-closed issues by default
            if 'status' not in self.params:
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
