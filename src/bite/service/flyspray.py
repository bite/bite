"""Web scraper for Flyspray."""

from dateutil.parser import parse as parsetime
from snakeoil.klass import aliased, alias

from ._csv import CSVRequest
from ._html import HTML
from ._reqs import URLRequest, URLParseRequest, req_cmd
from ..objects import Item, Comment, Attachment, TimeInterval
from ..exceptions import BiteError, RequestError


class FlysprayError(RequestError):
    """Flyspray service specific error."""

    def __init__(self, msg, code=None, text=None):
        msg = f'Flyspray error: {msg}'
        super().__init__(msg, code, text)


class FlysprayTicket(Item):

    attributes = {
        'cc': 'cc',
        'owner': 'Assignee',
        'reporter': 'Reporter',
    }

    attribute_aliases = {
        'title': 'summary',
        'created': 'date_opened',
        'closed': 'date_closed',
        'modified': 'lastedit',
    }

    _print_fields = (
        ('title', 'Title'),
        ('id', 'ID'),
        ('created', 'Reported'),
        ('modified', 'Updated'),
        ('status', 'Status'),
        ('resolution', 'Resolution'),
        ('reporter', 'Reporter'),
        ('owner', 'Assignee'),
        ('cc', 'CC'),
        ('component', 'Component'),
        ('priority', 'Priority'),
        ('keywords', 'Keywords'),
        ('version', 'Version'),
        ('platform', 'Platform'),
        ('milestone', 'Milestone'),
        ('difficulty', 'Difficulty'),
        ('type', 'Type'),
        ('wip', 'Completion'),
        ('severity', 'Severity'),
    )

    type = 'task'

    def __init__(self, get_desc=True, **kw):
        for k, v in kw.items():
            if not v:
                v = None
            setattr(self, k, v)

        self.comments = None
        self.attachments = None
        self.changes = None

        if get_desc and self.description:
            self.description = FlysprayComment(
                count=0, creator=self.reporter, created=self.created,
                text=self.description.strip())


class FlysprayComment(Comment):
    pass


class FlysprayAttachment(Attachment):
    pass


class FlysprayScraper(HTML):
    """Service supporting the Flyspray-based ticket trackers."""

    _service = 'flyspray-scraper'

    item = FlysprayTicket
    item_endpoint = 'index.php?do=details&task_id={id}'

    def __init__(self, max_results=None, **kw):
        super().__init__(max_results=max_results, **kw)


@req_cmd(FlysprayScraper, cmd='search')
class SearchRequest(URLParseRequest, CSVRequest, URLRequest):
    """Construct a web search request."""

    def __init__(self, get_desc=False, **kw):
        self._get_desc = get_desc
        super().__init__(endpoint='/index.php', **kw)
        # force the query to export a CSV doc back
        self.params['export_list'] = 'Export Tasklist'

    def parse(self, data):
        for item in data:
            yield self.service.item(get_desc=self._get_desc, **item)

    @aliased
    class ParamParser(URLParseRequest.ParamParser):

        _date_fields = {
            'modified': 'changed',
            'created': 'opened',
            'due': 'duedate',
            'closed': 'closed',
        }

        def _finalize(self, **kw):
            super()._finalize()

            # default to returning open tasks
            if 'status[]' not in self.params:
                self.params['status[]'] = 'open'

        def terms(self, k, v):
            self.params['string'] = ' '.join(v)
            self.options.append(f"Summary: {', '.join(v)}")

        def status(self, k, v):
            for x in v:
                self.params.add('status[]', x)
            self.options.append(f"Status: {', '.join(v)}")

        @alias('modified', 'due', 'closed')
        def created(self, k, v):
            if isinstance(v, (str, tuple)):
                v = TimeInterval(v)
            start, end = v
            if start:
                self.params[f'{self._date_fields[k]}from'] = start.isoformat()
            if end:
                self.params[f'{self._date_fields[k]}to'] = end.isoformat()
            self.options.append(f'{k.capitalize()}: {v}')
