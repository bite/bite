"""API access to Launchpad.

API docs:
    https://launchpad.net/+apidoc/
    https://help.launchpad.net/API/Hacking
"""

from dateutil.parser import parse as dateparse
from snakeoil.klass import aliased, alias

from ._jsonrest import JsonREST
from ._reqs import (
    OffsetPagedRequest, Request, BaseGetRequest, req_cmd, BaseCommentsRequest,
)
from ._rest import RESTRequest, RESTParseRequest
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

    def __init__(self, data_link, self_link, message_link, title, data=None, **kw):
        super().__init__(id=self_link.rsplit('/', 1)[1], filename=title, data=data)
        self.comment = message_link.rsplit('/', 1)[1]
        self.data_link = data_link


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
    # requires authentication to access -- non-auth endpoint requires the filename
    # attachment_endpoint = 'https://bugs.launchpad.net/bugs/{id}/+attachment/{a_id}'

    def __init__(self, base, **kw):
        # launchpad supports up to 300, but often times out for higher values
        kw['max_results'] = 100
        project = base.rstrip('/').rsplit('/', 1)[1]
        self._api_base = f"https://api.launchpad.net/1.0"
        super().__init__(endpoint=f"/{project}", base=self._api_base, **kw)
        self.webbase = base


class LaunchpadPagedRequest(OffsetPagedRequest, RESTRequest):

    _offset_key = 'ws.start'
    _size_key = 'ws.size'
    _total_key = 'total_size'


@req_cmd(Launchpad, cmd='search')
class _SearchRequest(RESTParseRequest, LaunchpadPagedRequest):
    """Construct a search request.

    API docs: https://launchpad.net/+apidoc/1.0.html#bugs under the 'searchTasks'
    for custom GET methods.
    """

    # map from standardized kwargs name to expected service parameter name
    _params_map = {
        'sort': 'order_by',
    }

    def parse(self, data):
        data = super().parse(data)
        bugs = data['entries']
        for bug in bugs:
            yield self.service.item(self.service, **bug)

    def handle_exception(self, e):
        if e.code == 400:
            raise LaunchpadError(msg=e.text, code=e.code)
        raise e

    @aliased
    class ParamParser(RESTParseRequest.ParamParser):

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

        def _finalize(self, **kw):
            if not self.params or self.params.keys() == {'sort'}:
                raise BiteError('no supported search terms or options specified')

            # default to sorting ascending by ID
            self.params.setdefault('sort', ['id'])

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
            self.params[k] = sorting_terms
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
        for i, bug in enumerate(data):
            yield self.service.item(service=self.service, **bug)


@req_cmd(Launchpad, cmd='comments')
class _CommentsRequest(BaseCommentsRequest):
    """Construct a comments request."""

    def __init__(self, **kw):
        super().__init__(**kw)
        if self.ids is None:
            raise ValueError(f'No IDs specified')

        self.options.append(f"IDs: {', '.join(map(str, self.ids))}")

        reqs = []
        for i in self.ids:
            reqs.extend([
                RESTRequest(
                    service=self.service, endpoint=f'{self.service._api_base}/bugs/{i}/messages'),
                RESTRequest(
                    service=self.service, endpoint=f'{self.service._api_base}/bugs/{i}/attachments'),
            ])

        self._reqs = tuple(reqs)

    def parse(self, data):
        def items():
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
        yield from self.filter(items())


@req_cmd(Launchpad, cmd='attachments')
class _AttachmentsRequest(Request):
    """Construct an attachments request."""

    def __init__(self, ids=(), attachment_ids=(), get_data=False, **kw):
        super().__init__(**kw)
        if not any((ids, attachment_ids)):
            raise ValueError('No ID(s) specified')

        reqs = []
        for i in ids:
            endpoint = f'{self.service._api_base}/bugs/{i}/attachments'
            reqs.append(RESTRequest(service=self.service, endpoint=endpoint))
        for i, a_ids in attachment_ids:
            for a_id in a_ids:
                endpoint = f'{self.service._api_base}/bugs/{i}/+attachment/{a_id}'
                reqs.append(RESTRequest(service=self.service, endpoint=endpoint))

        self.ids = ids
        self.attachment_ids = attachment_ids
        self._reqs = tuple(reqs)
        self._get_data = get_data

    def parse(self, data):
        # wrap data similar to how an item ID response looks
        if self.attachment_ids:
            data = [tuple(data)]

        for attachments in data:
            if self.ids:
                attachments = attachments['entries']
            if self._get_data:
                reqs = tuple(Request(
                    service=self.service, method='GET', url=x['data_link'], raw=True)
                    for x in attachments)
                content = Request(
                    service=self.service, reqs=reqs, raw=True).send(allow_redirects=True)
            else:
                content = self._none_gen
            yield tuple(self.service.attachment(data=c, **a)
                        for a, c in zip(attachments, content))


@req_cmd(Launchpad, cmd='get')
class _GetRequest(BaseGetRequest):
    pass
