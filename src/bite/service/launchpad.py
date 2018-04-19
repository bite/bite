"""API access to Launchpad.

API docs:
    https://launchpad.net/+apidoc/
    https://help.launchpad.net/API/Hacking
"""

from dateutil.parser import parse as dateparse

from . import RESTRequest, PagedRequest, req_cmd
from ..cache import Cache
from ..exceptions import RequestError, BiteError
from ._jsonrest import JsonREST
from ..objects import Item, Attachment, Comment


class LaunchpadError(RequestError):

    def __init__(self, msg, code=None, text=None):
        msg = 'Launchpad error: ' + msg
        super().__init__(msg, code, text)


class LaunchpadBug(Item):

    type = 'bug'


class LaunchpadBugTask(Item):

    attributes = {
        'owner': 'Assignee',
        'bug_commenter': 'Commenter',
        'bug_reporter': 'Reporter',
        'bug_subscriber': 'Subscriber',
        'has_cve': 'CVE',
        'has_patch': 'Patch',
        'date_created': 'Created',
        'created_since': 'Created',
        'modified_since': 'Modified',
        'title': 'Title',
    }

    attribute_aliases = {
        'created': 'date_created',
    }

    type = 'bug'

    def __init__(self, service, comments=None, attachments=None, **kw):
        self.service = service
        for k, v in kw.items():
            if k in ('date_created',):
                setattr(self, k, dateparse(v))
            elif k == 'owner_link':
                setattr(self, 'owner', v[len(service.base) + 2:])
            elif k == 'bug_link':
                setattr(self, 'id', v.rsplit('/', 1)[1])
            elif k == 'title':
                setattr(self, k, v.split(': ', 1)[1].strip('"'))
            else:
                setattr(self, k, v)

        self.attachments = attachments if attachments is not None else []
        self.comments = comments if comments is not None else []

    def __str__(self):
        lines = []
        print_fields = [
            ('title', 'Title'),
            ('date_created', 'Created'),
        ]

        for field, title in print_fields:
            value = getattr(self, field)
            if value is None:
                continue
            lines.append('{:<12}: {}'.format(title, value))

        return '\n'.join(lines)



class LaunchpadComment(Comment):
    pass


class LaunchpadAttachment(Attachment):
    pass


class LaunchpadCache(Cache):
    pass


class Launchpad(JsonREST):
    """Service supporting the Launchpad bug tracker."""

    _service = 'launchpad'
    _cache_cls = LaunchpadCache

    item = LaunchpadBug
    item_endpoint = '/+bug/'
    #attachment = LaunchpadAttachment
    # attachment_endpoint = '/file'

    def __init__(self, base, **kw):
        # launchpad supports up to 300, but often times out for higher values
        kw['max_results'] = 100
        project = base.rstrip('/').rsplit('/', 1)[1]
        api_base = f"https://api.launchpad.net/1.0"
        super().__init__(endpoint=f"/{project}", base=api_base, **kw)
        self.webbase = base


class LaunchpadPagedRequest(PagedRequest):
    """Keep requesting matching records until all relevant results are returned."""

    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        self._offset_key = 'ws.start'


@req_cmd(Launchpad, 'search')
class _SearchRequest(LaunchpadPagedRequest, RESTRequest):
    """Construct a search request.

    API docs: https://launchpad.net/+apidoc/1.0.html#bugs under the 'searchTasks'
    for custom GET methods.
    """

    # Map of allowed sorting input values to launchpad parameters determined by
    # looking at available values on the web interface.
    sorting_map = {
        'importance': 'importance',
        'status': 'status',
        'info-type': 'information_type',
        'id': 'id',
        'title': 'title',
        'target': 'targetname',
        'milestone': 'milestone_name',
        'modified': 'date_last_updated',
        'assignee': 'assignee',
        'creator': 'reporter',
        'created': 'datecreated',
        'tag': 'tag',
        'heat': 'heat',
    }

    def __init__(self, service, **kw):
        params, options = self.parse_params(service=service, **kw)
        if not params:
            raise BiteError('no supported search terms or options specified')

        params['ws.op'] = 'searchTasks'
        params['ws.size'] = service.max_results
        super().__init__(endpoint='', service=service, params=params, **kw)
        self.options = options

    def parse_params(self, service, params=None, options=None, **kw):
        params = params if params is not None else {}
        options = options if options is not None else []

        for k, v in ((k, v) for (k, v) in kw.items() if v):
            if k == 'terms':
                # default to searching for any matching terms
                params['search_text'] = ' OR '.join(v)
                options.append(f"Summary: {', '.join(map(str, v))}")
            elif k in ('owner', 'bug_commenter', 'bug_reporter', 'bug_subscriber'):
                # TODO: validate user exists
                # invalid users return HTTP Error 400
                # TODO: Allow searching by display name (will require making
                # query to find people first which would solve the validation
                # issue as well.
                params[k] = f"{service.base}/~{v}"
                options.append(f"{LaunchpadBugTask.attributes[k]}: {v}")
            elif k in ('created_since', 'modified_since'):
                params[k] = v.isoformat()
                options.append(f'{LaunchpadBugTask.attributes[k]}: {v} (since {v!r} UTC)')
            elif k in ('has_cve', 'has_patch'):
                # launchpad is particular about the boolean values it receives
                params[k] = str(v).lower()
                options.append(f"{LaunchpadBugTask.attributes[k]}: {v}")
            elif k == 'sort':
                sorting_terms = []
                for sort in v:
                    if sort[0] == '-':
                        key = sort[1:]
                        inverse = '-'
                    else:
                        key = sort
                        inverse = ''
                    try:
                        order_var = self.sorting_map[key]
                    except KeyError:
                        choices = ', '.join(sorted(self.sorting_map.keys()))
                        raise BiteError(
                            f'unable to sort by: {sort!r} (available choices: {choices}')
                    sorting_terms.append(f'{inverse}{order_var}')
                params['order_by'] = sorting_terms
                options.append(f"Sort order: {', '.join(v)}")

        return params, options

    def parse(self, data):
        if self._total is None:
            self._total = data['total_size']
        bugs = data['entries']
        for bug in bugs:
            yield LaunchpadBugTask(self.service, **bug)

    def handle_exception(self, e):
        if e.code == 400:
            raise LaunchpadError(msg=e.text, code=e.code)
        raise e
