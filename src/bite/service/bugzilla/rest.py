"""Support Bugzilla's REST interface."""

from collections import deque

from . import Bugzilla5_0, Bugzilla5_2
from .reqs import (
    LoginRequest, SearchRequest5_0, ChangesRequest, CommentsRequest, AttachmentsRequest,
    GetItemRequest, ModifyRequest, AttachRequest, CreateRequest,
    ExtensionsRequest, VersionRequest, FieldsRequest, ProductsRequest, UsersRequest,
)
from .._jsonrest import JsonREST
from .._reqs import req_cmd
from .._rest import RESTRequest


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


class Bugzilla5_2Rest(Bugzilla5_0Rest, Bugzilla5_2):
    """Service for Bugzilla 5.2 REST interface.

    API docs: http://bugzilla.readthedocs.io/en/latest/api/index.html
    """
    _service = 'bugzilla5.2-rest'


@req_cmd(Bugzilla5_0Rest, cmd='modify', obj_args=True)
class _ModifyRequest(ModifyRequest, RESTRequest):
    def __init__(self, **kw):
        super().__init__(endpoint='/bug', method='PUT', **kw)
        self.endpoint = f"/bug/{self.params['ids'][0]}"

    def params_to_data(self):
        super().params_to_data()
        if self.data['ids'][1:]:
            self.data['ids'] = self.params['ids'][1:]
        else:
            del self.data['ids']


@req_cmd(Bugzilla5_0Rest, cmd='attach', obj_args=True)
class _AttachRequest(AttachRequest, RESTRequest):
    def __init__(self, **kw):
        super().__init__(endpoint='/bug/{}/attachment', method='POST', **kw)
        self.endpoint = self.endpoint.format(self.params['ids'][0])

    def params_to_data(self):
        super().params_to_data()
        if self.data['ids'][1:]:
            self.data['ids'] = self.params['ids'][1:]
        else:
            del self.data['ids']


@req_cmd(Bugzilla5_0Rest, cmd='create', obj_args=True)
class _CreateRequest(CreateRequest, RESTRequest):
    def __init__(self, **kw):
        super().__init__(endpoint='/bug', method='POST', **kw)


@req_cmd(Bugzilla5_0Rest, cmd='search')
class _SearchRequest5_0(SearchRequest5_0, RESTRequest):
    def __init__(self, **kw):
        super().__init__(endpoint='/bug', **kw)


@req_cmd(Bugzilla5_0Rest, cmd='changes')
class _ChangesRequest(ChangesRequest, RESTRequest):
    def __init__(self, **kw):
        super().__init__(endpoint='/bug/{}/history', **kw)
        self.endpoint = self.endpoint.format(self.params['ids'][0])
        self.params['ids'] = self.params['ids'][1:]


@req_cmd(Bugzilla5_0Rest, cmd='comments')
class _CommentsRequest(CommentsRequest, RESTRequest):
    def __init__(self, **kw):
        super().__init__(endpoint='/bug/{}/comment', **kw)
        self.endpoint = self.endpoint.format(self.params['ids'][0])
        self.params['ids'] = self.params['ids'][1:]


@req_cmd(Bugzilla5_0Rest, cmd='attachments')
class _AttachmentsRequest(AttachmentsRequest, RESTRequest):
    def __init__(self, **kw):
        super().__init__(endpoint='/bug/{}/attachment', **kw)
        if 'ids' in self.params:
            self.endpoint = self.endpoint.format(self.params['ids'][0])
            self.params['ids'] = self.params['ids'][1:]
        else:
            self.endpoint = f"/bug/attachment/{self.params['attachment_ids'][0]}"
            self.params['attachment_ids'] = self.params['attachment_ids'][1:]


@req_cmd(Bugzilla5_0Rest)
class _GetItemRequest(GetItemRequest, RESTRequest):
    def __init__(self, **kw):
        super().__init__(endpoint='/bug', method='GET', **kw)
        # REST interface renames 'ids' param to 'id'
        self.params['id'] = self.params.pop('ids')


@req_cmd(Bugzilla5_0Rest)
class _LoginRequest(LoginRequest, RESTRequest):
    """Construct a login request.

    API docs: https://bugzilla.readthedocs.io/en/latest/api/core/v1/user.html#login
    """

    def __init__(self, **kw):
        super().__init__(endpoint='/login', **kw)


@req_cmd(Bugzilla5_0Rest, cmd='extensions')
class _ExtensionsRequest(ExtensionsRequest, RESTRequest):
    """Construct an extensions request.

    API docs: https://bugzilla.readthedocs.io/en/latest/api/core/v1/bugzilla.html#extensions
    """

    def __init__(self, **kw):
        super().__init__(endpoint='/extensions', **kw)


@req_cmd(Bugzilla5_0Rest, cmd='version')
class _VersionRequest(VersionRequest, RESTRequest):
    """Construct a version request.

    API docs: https://bugzilla.readthedocs.io/en/latest/api/core/v1/bugzilla.html#version
    """

    def __init__(self, **kw):
        super().__init__(endpoint='/version', **kw)


@req_cmd(Bugzilla5_0Rest, cmd='fields')
class _FieldsRequest(FieldsRequest, RESTRequest):
    """Construct a fields request.

    API docs: https://bugzilla.readthedocs.io/en/latest/api/core/v1/field.html#fields
    """

    def __init__(self, **kw):
        super().__init__(endpoint='/field/bug', **kw)
        # use the first parameter for the base url then add any leftovers
        if self.params:
            params = deque((k, i) for k, v in self.params.items() for i in v)
            self.endpoint = '{}/{}'.format(self.endpoint, params.popleft()[1])
            self.params = dict(params)


@req_cmd(Bugzilla5_0Rest, cmd='products')
class _ProductsRequest(ProductsRequest, RESTRequest):
    """Construct a products request.

    API docs: https://bugzilla.readthedocs.io/en/latest/api/core/v1/product.html#get-product
    """

    def __init__(self, **kw):
        super().__init__(endpoint='/product', **kw)


@req_cmd(Bugzilla5_0Rest, cmd='users')
class _UsersRequest(UsersRequest, RESTRequest):
    """Construct a users request.

    API docs: https://bugzilla.readthedocs.io/en/latest/api/core/v1/user.html#get-user
    """

    def __init__(self, **kw):
        super().__init__(endpoint='/user', **kw)
