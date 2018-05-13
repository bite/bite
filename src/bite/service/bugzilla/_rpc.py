from . import Bugzilla, Bugzilla5_0, Bugzilla5_2
from .reqs import (
    SearchRequest4_4, SearchRequest5_0, ChangesRequest, CommentsRequest,
    AttachmentsRequest, LoginRequest, GetItemRequest, ModifyRequest,
    AttachRequest, CreateRequest, ExtensionsRequest, VersionRequest, FieldsRequest,
    ProductsRequest, UsersRequest,
)
from .._reqs import req_cmd
from .._rpc import RPCRequest


class Bugzilla4_4Rpc(Bugzilla):
    """Support bugzilla 4.4 RPC calls."""


class Bugzilla5_0Rpc(Bugzilla4_4Rpc, Bugzilla5_0):
    """Support bugzilla 5.0 RPC calls."""


class Bugzilla5_2Rpc(Bugzilla5_0Rpc, Bugzilla5_2):
    """Support bugzilla 5.2 RPC calls."""


@req_cmd(Bugzilla4_4Rpc)
class _LoginRequest(LoginRequest, RPCRequest):
    def __init__(self, **kw):
        super().__init__(command='User.login', **kw)


@req_cmd(Bugzilla4_4Rpc, cmd='users')
class _UsersRequest(UsersRequest, RPCRequest):
    def __init__(self, **kw):
        super().__init__(command='User.get', **kw)


@req_cmd(Bugzilla4_4Rpc, cmd='fields')
class _FieldsRequest(FieldsRequest, RPCRequest):
    def __init__(self, **kw):
        super().__init__(command='Bug.fields', **kw)


@req_cmd(Bugzilla4_4Rpc, cmd='products')
class _ProductsRequest(ProductsRequest, RPCRequest):
    def __init__(self, **kw):
        super().__init__(command='Product.get', **kw)


@req_cmd(Bugzilla4_4Rpc, cmd='extensions')
class _ExtensionsRequest(ExtensionsRequest, RPCRequest):
    def __init__(self, **kw):
        super().__init__(command='Bugzilla.extensions', **kw)


@req_cmd(Bugzilla4_4Rpc, cmd='version')
class _VersionRequest(VersionRequest, RPCRequest):
    def __init__(self, **kw):
        super().__init__(command='Bugzilla.version', **kw)


@req_cmd(Bugzilla4_4Rpc, cmd='search')
class _SearchRequest4_4(SearchRequest4_4, RPCRequest):
    def __init__(self, **kw):
        super().__init__(command='Bug.search', **kw)


@req_cmd(Bugzilla5_0Rpc, cmd='search')
class _SearchRequest5_0(SearchRequest5_0, RPCRequest):
    def __init__(self, **kw):
        super().__init__(command='Bug.search', **kw)


@req_cmd(Bugzilla4_4Rpc, cmd='changes')
class _ChangesRequest(ChangesRequest, RPCRequest):
    def __init__(self, **kw):
        super().__init__(command='Bug.history', **kw)


@req_cmd(Bugzilla4_4Rpc, cmd='comments')
class _CommentsRequest(CommentsRequest, RPCRequest):
    def __init__(self, **kw):
        super().__init__(command='Bug.comments', **kw)


@req_cmd(Bugzilla4_4Rpc, cmd='attachments')
class _AttachmentsRequest(AttachmentsRequest, RPCRequest):
    def __init__(self, **kw):
        super().__init__(command='Bug.attachments', **kw)


@req_cmd(Bugzilla4_4Rpc)
class _GetItemRequest(GetItemRequest, RPCRequest):
    def __init__(self, **kw):
        super().__init__(command='Bug.get', **kw)
        # return array of faults for bad bugs instead of directly failing out
        self.params['permissive'] = True


@req_cmd(Bugzilla4_4Rpc, cmd='modify', obj_args=True)
class _ModifyRequest(ModifyRequest, RPCRequest):
    def __init__(self, **kw):
        super().__init__(command='Bug.update', **kw)


@req_cmd(Bugzilla4_4Rpc, cmd='attach', obj_args=True)
class _AttachRequest(AttachRequest, RPCRequest):
    def __init__(self, **kw):
        super().__init__(command='Bug.add_attachment', **kw)


@req_cmd(Bugzilla4_4Rpc, cmd='create', obj_args=True)
class _CreateRequest(CreateRequest, RPCRequest):
    def __init__(self, **kw):
        super().__init__(command='Bug.create', **kw)
