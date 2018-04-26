"""Support Sourceforge's REST interface.

API docs:
    https://sourceforge.net/p/forge/documentation/API/
    https://sourceforge.net/p/forge/documentation/Allura%20API/
"""

from dateutil.parser import parse as dateparse

from ._jsonrest import JsonREST
from ._reqs import RESTRequest, PagedRequest, req_cmd
from ..exceptions import BiteError, RequestError
from ..objects import Item


class SourceforgeError(RequestError):
    """Sourceforge service specific error."""

    def __init__(self, msg, code=None, text=None):
        msg = f'Sourceforge error: {msg}'
        super().__init__(msg, code, text)


class SourceforgeTicket(Item):

    attributes = {
        'status': 'Status',
        'created_date': 'Created',
        'mod_date': 'Modified',
        'assigned_to': 'Assignee',
        'reported_by': 'Reporter',
        'summary': 'Title',
        'ticket_num': 'ID',
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
        ('created_date', 'Created'),
        ('mod_date', 'Modified'),
        ('comments', 'Comments'),
        ('attachments', 'Attachments'),
        ('changes', 'Changes'),
    )

    # Defaults to ticket; however, projects can choose what they call it so
    # it's overridden per service instance.
    type = 'ticket'

    def __init__(self, service, ticket, get_desc=True):
        for k in self.attributes.keys():
            v = ticket.get(k, None)
            if k in ('created_date', 'mod_date') and v:
                v = dateparse(v)
            setattr(self, k, v)


class Sourceforge(JsonREST):
    """Service supporting the Sourceforge trackers."""

    _service = 'sourceforge'

    item = SourceforgeTicket
    item_endpoint = '/{id}'

    def __init__(self, base, max_results=None, **kw):
        try:
            api_base, project = base.split('/p/', 1)
            project, tracker = project.strip('/').split('/', 1)
        except ValueError as e:
            raise BiteError(f'invalid project base: {base!r}')

        endpoint = f'/rest/p/{project}/{tracker}'
        # Sourceforge allows projects to name/mount their ticket trackers under
        # any name (e.g. issues, bugs, tickets), try to determine the item name from this.
        self.item.type = tracker.rstrip('s')

        # 500 results appears to be the default maximum
        if max_results is None:
            max_results = 500
        super().__init__(
            endpoint=endpoint, base=api_base, max_results=max_results, **kw)

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
        """Handle Sourceforge specific errors."""
        raise SourceforgeError(msg=msg, code=code)


@req_cmd(Sourceforge, 'search')
class _SearchRequest(PagedRequest, RESTRequest):
    """Construct a search request.

    Currently using on Solr on the backend, see the following docs for query help:
        https://lucene.apache.org/solr/guide/7_3/the-standard-query-parser.html
        http://www.solrtutorial.com/solr-query-syntax.html
        http://yonik.com/solr/
    """

    _page_key = 'page'
    _size_key = 'limit'
    _total_key = 'count'

    # Map of allowed sorting input values to service parameters.
    sorting_map = {
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
        'milestone': '_milestone_s',
        'type': '_type_s',
        'needs': '_needs_s',
        'patch': '_patch_s',
    }

    def __init__(self, service, **kw):
        params, options = self.parse_params(service=service, **kw)
        if not params:
            raise BiteError('no supported search terms or options specified')

        super().__init__(service=service, endpoint='/search', params=params, **kw)
        self.options = options

    def parse_params(self, service, params=None, options=None, **kw):
        params = params if params is not None else {}
        options = options if options is not None else []

        for k, v in ((k, v) for (k, v) in kw.items() if v):
            if k == 'terms':
                params['q'] = '+'.join(v)
                options.append(f"Summary: {', '.join(v)}")
            elif k == 'sort':
                sorting_terms = []
                for sort in v:
                    if sort[0] == '-':
                        key = sort[1:]
                        order = 'desc'
                    else:
                        key = sort
                        order = 'asc'
                    try:
                        order_var = self.sorting_map[key]
                    except KeyError:
                        choices = ', '.join(sorted(self.sorting_map.keys()))
                        raise BiteError(
                            f'unable to sort by: {key!r} (available choices: {choices}')
                    sorting_terms.append(f'{order_var} {order}')
                params['sort'] = ','.join(sorting_terms)
                options.append(f"Sort order: {', '.join(v)}")

        # default to sorting ascending by ID
        if 'sort' not in params:
            params['sort'] = 'ticket_num_i asc'

        return params, options

    def parse(self, data):
        super().parse(data)
        tickets = data['tickets']
        for ticket in tickets:
            yield self.service.item(self.service, ticket)
