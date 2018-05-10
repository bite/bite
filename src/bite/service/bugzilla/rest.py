"""Support Bugzilla's REST interface."""

from collections import deque

from . import Bugzilla5_0, Bugzilla5_2
from .objects import BugzillaBug
from .reqs import (
    LoginRequest, SearchRequest5_0, ChangesRequest, CommentsRequest, AttachmentsRequest,
    GetItemRequest, ModifyRequest, AttachRequest, CreateRequest,
    ExtensionsRequest, VersionRequest, FieldsRequest, ProductsRequest, UsersRequest,
)
from .._jsonrest import JsonREST
from .._reqs import RESTRequest, GetRequest, req_cmd


class _BugzillaRestBase(Bugzilla5_0, JsonREST):
    """Base service class for Bugzilla REST interface."""

    def __init__(self, **kw):
        super().__init__(endpoint='/rest', **kw)

    def parse_response(self, response):
        data = super().parse_response(response)
        if 'error' not in data:
            return data
        else:
            self.handle_error(code=data['code'], msg=data['message'])


class Bugzilla5_0Rest(_BugzillaRestBase):
    """Service for Bugzilla 5.0 REST interface.

    API docs: http://bugzilla.readthedocs.io/en/5.0/api/index.html
    """
    _service = 'bugzilla5.0-rest'


class Bugzilla5_2Rest(Bugzilla5_2, Bugzilla5_0Rest):
    """Service for Bugzilla 5.2 REST interface.

    API docs: http://bugzilla.readthedocs.io/en/latest/api/index.html
    """
    _service = 'bugzilla5.2-rest'


@req_cmd(Bugzilla5_0Rest, cmd='get')
class _GetRequest(GetRequest):
    """Construct a get request."""


@req_cmd(Bugzilla5_0Rest, cmd='modify', obj_args=True)
class _ModifyRequest(RESTRequest, ModifyRequest):
    def __init__(self, *args, **kw):
        """Construct a modify request."""
        super().__init__(endpoint='/bug', method='PUT', *args, **kw)
        self.endpoint = f"/bug/{self.params['ids'][0]}"

    def params_to_data(self):
        super().params_to_data()
        if self.data['ids'][1:]:
            self.data['ids'] = self.params['ids'][1:]
        else:
            del self.data['ids']


@req_cmd(Bugzilla5_0Rest, cmd='attach', obj_args=True)
class _AttachRequest(RESTRequest, AttachRequest):
    def __init__(self, *args, **kw):
        """Construct a modify request."""
        super().__init__(endpoint='/bug/{}/attachment', method='POST', *args, **kw)
        self.endpoint = self.endpoint.format(self.params['ids'][0])

    def params_to_data(self):
        super().params_to_data()
        if self.data['ids'][1:]:
            self.data['ids'] = self.params['ids'][1:]
        else:
            del self.data['ids']


@req_cmd(Bugzilla5_0Rest, cmd='create', obj_args=True)
class _CreateRequest(RESTRequest, CreateRequest):
    def __init__(self, *args, **kw):
        """Construct a create request."""
        super().__init__(endpoint='/bug', method='POST', *args, **kw)


@req_cmd(Bugzilla5_0Rest, cmd='search')
class _SearchRequest5_0(RESTRequest, SearchRequest5_0):
    def __init__(self, *args, **kw):
        """Construct a search request."""
        super().__init__(endpoint='/bug', *args, **kw)


@req_cmd(Bugzilla5_0Rest, cmd='changes')
class _ChangesRequest(RESTRequest, ChangesRequest):
    def __init__(self, *args, **kw):
        """Construct a changes request."""
        super().__init__(endpoint='/bug/{}/history', *args, **kw)
        self.endpoint = self.endpoint.format(self.params['ids'][0])
        self.params['ids'] = self.params['ids'][1:]


@req_cmd(Bugzilla5_0Rest, cmd='comments')
class _CommentsRequest(RESTRequest, CommentsRequest):
    def __init__(self, *args, **kw):
        """Construct a comments request."""
        super().__init__(endpoint='/bug/{}/comment', *args, **kw)
        self.endpoint = self.endpoint.format(self.params['ids'][0])
        self.params['ids'] = self.params['ids'][1:]


@req_cmd(Bugzilla5_0Rest, cmd='attachments')
class _AttachmentsRequest(RESTRequest, AttachmentsRequest):
    def __init__(self, *args, **kw):
        """Construct an attachments request."""
        super().__init__(endpoint='/bug/{}/attachment', *args, **kw)
        if 'ids' in self.params:
            self.endpoint = self.endpoint.format(self.params['ids'][0])
            self.params['ids'] = self.params['ids'][1:]
        else:
            self.endpoint = f"/bug/attachment/{self.params['attachment_ids'][0]}"
            self.params['attachment_ids'] = self.params['attachment_ids'][1:]


@req_cmd(Bugzilla5_0Rest)
class _GetItemRequest(RESTRequest, GetItemRequest):
    def __init__(self, *args, **kw):
        """Construct a get request."""
        super().__init__(endpoint='/bug', method='GET', *args, **kw)
        # REST interface renames 'ids' param to 'id'
        self.params['id'] = self.params.pop('ids')


@req_cmd(Bugzilla5_0Rest)
class _LoginRequest(RESTRequest, LoginRequest):
    def __init__(self, *args, **kw):
        """Construct a login request."""
        super().__init__(endpoint='/login', *args, **kw)


@req_cmd(Bugzilla5_0Rest, cmd='extensions')
class _ExtensionsRequest(RESTRequest, ExtensionsRequest):
    def __init__(self, service):
        """Construct an extensions request."""
        super().__init__(service=service, endpoint='/extensions')


@req_cmd(Bugzilla5_0Rest, cmd='version')
class _VersionRequest(RESTRequest, VersionRequest):
    def __init__(self, service):
        """Construct a version request."""
        super().__init__(service=service, endpoint='/version')


@req_cmd(Bugzilla5_0Rest, cmd='fields')
class _FieldsRequest(RESTRequest, FieldsRequest):
    def __init__(self, *args, **kw):
        super().__init__(endpoint='/field/bug', *args, **kw)
        # use the first parameter for the base url then add any leftovers
        if self.params:
            params = deque((k, i) for k, v in self.params.items() for i in v)
            self.endpoint = '{}/{}'.format(self.endpoint, params.popleft()[1])
            self.params = dict(params)


@req_cmd(Bugzilla5_0Rest, cmd='products')
class _ProductsRequest(RESTRequest, ProductsRequest):
    def __init__(self, *args, **kw):
        super().__init__(endpoint='/product', *args, **kw)


@req_cmd(Bugzilla5_0Rest, cmd='users')
class _UsersRequest(RESTRequest, UsersRequest):
    def __init__(self, *args, **kw):
        super().__init__(endpoint='/user', *args, **kw)
