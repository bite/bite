"""API access to Launchpad.

API docs:
    https://launchpad.net/+apidoc/
    https://help.launchpad.net/API/Hacking
"""

from dateutil.parser import parse as dateparse
from snakeoil.klass import aliased, alias

from ._jsonrest import JsonREST
from ._reqs import (
    OffsetPagedRequest, Request, GetRequest, ParseRequest,
    req_cmd, generator,
)
from ._rest import RESTRequest
from ..cache import Cache
from ..exceptions import RequestError, BiteError
from ..objects import Item, Attachment, Comment, Change


class LaunchpadError(RequestError):

    def __init__(self, msg, code=None, text=None):
        msg = 'Launchpad error: ' + msg
        super().__init__(msg, code, text)


class LaunchpadBug(Item):

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
        'modified': 'date_last_updated',
    }

    type = 'bug'

    def __init__(self, service, **kw):
        # Bug task objects are different from bug objects but both need to be
        # combined for full bug info. Searches return collections of bug tasks,
        # but performing 'get' actions needs to combine both bug and bug task
        # objects.
        if 'bug_link' in kw:
            bug_task = True
        else:
            bug_task = False

        for k, v in kw.items():
            if k in ('date_created', 'date_last_updated'):
                setattr(self, k, dateparse(v))
            elif k == 'owner_link':
                setattr(self, 'owner', v[len(service.base) + 2:])
            elif bug_task and k == 'bug_link':
                setattr(self, 'id', v.rsplit('/', 1)[1])
            elif bug_task and k == 'title':
                setattr(self, k, v.split(': ', 1)[1].strip('"'))
            else:
                setattr(self, k, v)


class LaunchpadComment(Comment):
    pass


class LaunchpadAttachment(Attachment):

    def __init__(self, data_link, self_link, message_link, title, **kw):
        super().__init__(id=self_link.rsplit('/', 1)[1], filename=title)
        self.comment = message_link.rsplit('/', 1)[1]
        self.data_link = data_link

    def read(self):
        # need to pull data from the data_link attr here
        raise NotImplementedError


class LaunchpadEvent(Change):
    pass


# TODO: cache project milestones
# (e.g. list URI https://api.launchpad.net/1.0/ubuntu/all_milestones)
class LaunchpadCache(Cache):
    pass


class Launchpad(JsonREST):
    """Service supporting the Launchpad bug tracker."""

    _service = 'launchpad'
    _cache_cls = LaunchpadCache

    item = LaunchpadBug
    item_endpoint = 'https://bugs.launchpad.net/bugs/{id}'
    attachment = LaunchpadAttachment
    # attachment_endpoint = '/file'

    def __init__(self, base, **kw):
        # launchpad supports up to 300, but often times out for higher values
        kw['max_results'] = 100
        project = base.rstrip('/').rsplit('/', 1)[1]
        self._api_base = f"https://api.launchpad.net/1.0"
        super().__init__(endpoint=f"/{project}", base=self._api_base, **kw)
        self.webbase = base


class LaunchpadPagedRequest(RESTRequest, OffsetPagedRequest):

    _offset_key = 'ws.start'
    _size_key = 'ws.size'
    _total_key = 'total_size'


@req_cmd(Launchpad, cmd='search')
class _SearchRequest(LaunchpadPagedRequest, ParseRequest):
    """Construct a search request.

    API docs: https://launchpad.net/+apidoc/1.0.html#bugs under the 'searchTasks'
    for custom GET methods.
    """

    def parse(self, data):
        super().parse(data)
        bugs = data['entries']
        for bug in bugs:
            yield self.service.item(self.service, **bug)

    def handle_exception(self, e):
        if e.code == 400:
            raise LaunchpadError(msg=e.text, code=e.code)
        raise e

    @aliased
    class ParamParser(ParseRequest.ParamParser):

        # Map of allowed sorting input values to service parameters determined by
        # looking at available values on the web interface.
        _sorting_map = {
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

        # Map of allowed status input values to launchpad parameters determined by
        # submitting an invalid value which returns an error message listing the
        # valid choices.
        _status_map = {
            'new': 'New',
            'incomplete': 'Incomplete',
            'opinion': 'Opinion',
            'invalid': 'Invalid',
            'wont-fix': "Won't Fix",
            'expired': 'Expired',
            'confirmed': 'Confirmed',
            'triaged': 'Triaged',
            'in-progress': 'In Progress',
            'committed': 'Fix Committed',
            'released': 'Fix Released',
            'incomplete-response': 'Incomplete (with response)',
            'incomplete-noresponse': 'Incomplete (without response)',
        }

        # Map of allowed importance input values to launchpad parameters determined by
        # submitting an invalid value which returns an error message listing the
        # valid choices.
        _importance_map = {
            'unknown': 'Unknown',
            'undecided': 'Undecided',
            'low': 'Low',
            'medium': "Medium",
            'high': 'High',
            'critical': 'Critical',
            'wishlist': 'Wishlist',
        }

        def __init__(self, *args, **kw):
            super().__init__(*args, **kw)
            self._sort = None

        def _finalize(self, **kw):
            if not self.params:
                raise BiteError('no supported search terms or options specified')

            # default to sorting ascending by ID
            self.params['order_by'] = self._sort if self._sort is not None else ['id']

            # launchpad operation flag for searching
            self.params['ws.op'] = 'searchTasks'

        def terms(self, k, v):
            # default to searching for any matching terms
            self.params['search_text'] = ' OR '.join(v)
            self.options.append(f"Summary: {', '.join(map(str, v))}")

        @alias('bug_commenter', 'bug_reporter', 'bug_subscriber')
        def owner(self, k, v):
            # TODO: validate user exists
            # invalid users return HTTP Error 400
            # TODO: Allow searching by display name (will require making
            # query to find people first which would solve the validation
            # issue as well.
            self.params[k] = f"{self.service.base}/~{v}"
            self.options.append(f"{self.service.item.attributes[k]}: {v}")

        @alias('modified_since')
        def created_since(self, k, v):
            self.params[k] = v.isoformat()
            self.options.append(f'{self.service.item.attributes[k]}: {v} (since {v!r} UTC)')

        @alias('has_patch')
        def has_cve(self, k, v):
            # launchpad is particular about the boolean values it receives
            self.params[k] = str(v).lower()
            self.options.append(f"{self.service.item.attributes[k]}: {v}")

        def omit_duplicates(self, k, v):
            # launchpad is particular about the boolean values it receives
            self.params[k] = str(v).lower()
            self.options.append(f"Show duplicates: {v}")

        def milestone(self, k, v):
            # TODO: verify milestone against cached list
            self.params[k] = f"{self.service._base}/+milestone/{v}"
            self.options.append(f"{k.capitalize()}: {v}")

        def importance(self, k, v):
            importances = []
            for importance in v:
                try:
                    importance_var = self._importance_map[importance]
                except KeyError:
                    choices = ', '.join(sorted(self._importance_map.keys()))
                    raise BiteError(
                        f'invalid importance: {importance!r} (available choices: {choices}')
                importances.append(importance_var)
            self.params[k] = importances
            self.options.append(f"{k.capitalize()}: {', '.join(v)}")

        def status(self, k, v):
            statuses = []
            for status in v:
                try:
                    status_var = self._status_map[status]
                except KeyError:
                    choices = ', '.join(sorted(self._status_map.keys()))
                    raise BiteError(
                        f'invalid status: {status!r} (available choices: {choices}')
                statuses.append(status_var)
            self.params[k] = statuses
            self.options.append(f"{k.capitalize()}: {', '.join(v)}")

        def sort(self, k, v):
            sorting_terms = []
            for sort in v:
                if sort[0] == '-':
                    key = sort[1:]
                    inverse = '-'
                else:
                    key = sort
                    inverse = ''
                try:
                    order_var = self._sorting_map[key]
                except KeyError:
                    choices = ', '.join(sorted(self._sorting_map.keys()))
                    raise BiteError(
                        f'unable to sort by: {key!r} (available choices: {choices}')
                sorting_terms.append(f'{inverse}{order_var}')
            self._sort = sorting_terms
            self.options.append(f"Sort order: {', '.join(v)}")

        def tags(self, k, v):
            tags = [x.lower() for x in v]
            if len(tags) > 1:
                combine = 'Any'
            else:
                tags = tags[0].split()
                combine = 'All'
            self.params[k] = tags
            self.params['tags_combinator'] = combine
            self.options.append(f"{k.capitalize()}: {combine} tags matching: {', '.join(tags)}")


@req_cmd(Launchpad)
class _GetItemRequest(Request):
    """Construct a bug request."""

    def __init__(self, ids, **kw):
        super().__init__(**kw)
        if ids is None:
            raise ValueError(f'No {self.service.item.type} specified')

        reqs = []
        for i in ids:
            endpoint = f'{self.service._api_base}/bugs/{i}'
            reqs.append(RESTRequest(service=self.service, endpoint=endpoint))

        self.ids = ids
        self._reqs = tuple(reqs)

    def parse(self, data):
        # TODO: hack, rework the http send parsing rewapper to be more
        # intelligent about unwrapping responses
        if len(self.ids) == 1:
            data = [data]
        for i, bug in enumerate(data):
            yield self.service.item(service=self.service, **bug)


@req_cmd(Launchpad, cmd='comments')
class _CommentsRequest(Request):
    """Construct a comments request."""

    def __init__(self, ids=None, created=None, service=None, **kw):
        if ids is None:
            raise ValueError(f'No {service.item.type} specified')

        reqs = []
        for i in ids:
            reqs.extend([
                RESTRequest(
                    service=service, endpoint=f'{service._api_base}/bugs/{i}/messages'),
                RESTRequest(
                    service=service, endpoint=f'{service._api_base}/bugs/{i}/attachments'),
            ])


        super().__init__(service=service, reqs=reqs)
        self.ids = ids

    @generator
    def parse(self, data):
        # merge attachments into related comments similar to the web UI
        for id in self.ids:
            comments = next(data)['entries']
            attachments = next(data)['entries']
            d = {}
            for a in attachments:
                comment_num = int(a['message_link'].rsplit('/', 1)[1])
                attachment_id = a['self_link'].rsplit('/', 1)[1]
                d[comment_num] = (attachment_id, a['title'])
            l = []
            for i, c in enumerate(comments):
                text = []
                if i in d:
                    text.append(f'Attachment: [{d[i][0]}] [{d[i][1]}]')
                if c['content']:
                    text.append(c['content'])
                text = '\n\n'.join(text)
                l.append(LaunchpadComment(
                    id=id, count=i, text=text,
                    created=dateparse(c['date_created']),
                    creator=c['owner_link'][len(self.service.base) + 2:]))
            yield tuple(l)


@req_cmd(Launchpad, cmd='attachments')
class _AttachmentsRequest(Request):
    """Construct an attachments request."""

    def __init__(self, ids=None, get_data=False, *args, **kw):
        super().__init__(**kw)
        if ids is None:
            raise ValueError(f'No {self.service.item.type} specified')

        reqs = []
        for i in ids:
            endpoint = f'{self.service._api_base}/bugs/{i}/attachments'
            reqs.append(RESTRequest(service=self.service, endpoint=endpoint))

        self.ids = ids
        self._reqs = tuple(reqs)

    @generator
    def parse(self, data):
        for attachments in data:
            attachments = attachments['entries']
            yield tuple(self.service.attachment(**a) for a in attachments)


@req_cmd(Launchpad, cmd='get')
class _GetRequest(GetRequest):
    pass
