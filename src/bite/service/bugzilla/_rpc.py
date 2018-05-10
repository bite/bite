from . import Bugzilla, Bugzilla5_0, Bugzilla5_2
from .reqs import (
    SearchRequest4_4, SearchRequest5_0, ChangesRequest, CommentsRequest,
    AttachmentsRequest, LoginRequest, GetItemRequest, ModifyRequest,
    AttachRequest, CreateRequest, ExtensionsRequest, VersionRequest, FieldsRequest,
    ProductsRequest, UsersRequest,
)
from .._reqs import GetRequest, req_cmd
from .._rpc import RPCRequest


class Bugzilla4_4Rpc(Bugzilla):
    """Support bugzilla 4.4 RPC calls."""


class Bugzilla5_0Rpc(Bugzilla5_0, Bugzilla4_4Rpc):
    """Support bugzilla 5.0 RPC calls."""


class Bugzilla5_2Rpc(Bugzilla5_2, Bugzilla5_0Rpc):
    """Support bugzilla 5.2 RPC calls."""


@req_cmd(Bugzilla4_4Rpc)
class _LoginRequest(RPCRequest, LoginRequest):
    def __init__(self, *args, **kw):
        super().__init__(method='User.login', *args, **kw)


@req_cmd(Bugzilla4_4Rpc, cmd='users')
class _UsersRequest(RPCRequest, UsersRequest):
    def __init__(self, *args, **kw):
        super().__init__(method='User.get', *args, **kw)


@req_cmd(Bugzilla4_4Rpc, cmd='fields')
class _FieldsRequest(RPCRequest, FieldsRequest):
    def __init__(self, *args, **kw):
        super().__init__(method='Bug.fields', *args, **kw)


@req_cmd(Bugzilla4_4Rpc, cmd='products')
class _ProductsRequest(RPCRequest, ProductsRequest):
    def __init__(self, *args, **kw):
        super().__init__(method='Product.get', *args, **kw)


@req_cmd(Bugzilla4_4Rpc, cmd='extensions')
class _ExtensionsRequest(RPCRequest, ExtensionsRequest):
    def __init__(self, *args, **kw):
        """Construct an extensions request."""
        super().__init__(method='Bugzilla.extensions', *args, **kw)


@req_cmd(Bugzilla4_4Rpc, cmd='version')
class _VersionRequest(RPCRequest, VersionRequest):
    def __init__(self, *args, **kw):
        """Construct a version request."""
        super().__init__(method='Bugzilla.version', *args, **kw)


@req_cmd(Bugzilla4_4Rpc, cmd='get')
class _GetRequest(GetRequest):
    def __init__(self, *args, **kw):
        """Construct a get request."""
        super().__init__(*args, **kw)


@req_cmd(Bugzilla4_4Rpc, cmd='search')
class _SearchRequest4_4(RPCRequest, SearchRequest4_4):
    def __init__(self, *args, **kw):
        """Construct a search request."""
        super().__init__(method='Bug.search', *args, **kw)


@req_cmd(Bugzilla5_0Rpc, cmd='search')
class _SearchRequest5_0(RPCRequest, SearchRequest5_0):
    def __init__(self, *args, **kw):
        """Construct a search request."""
        super().__init__(method='Bug.search', *args, **kw)


@req_cmd(Bugzilla4_4Rpc, cmd='changes')
class _ChangesRequest(RPCRequest, ChangesRequest):
    def __init__(self, *args, **kw):
        """Construct a changes request."""
        super().__init__(method='Bug.history', *args, **kw)


@req_cmd(Bugzilla4_4Rpc, cmd='comments')
class _CommentsRequest(RPCRequest, CommentsRequest):
    def __init__(self, *args, **kw):
        """Construct a comments request."""
        super().__init__(method='Bug.comments', *args, **kw)


@req_cmd(Bugzilla4_4Rpc, cmd='attachments')
class _AttachmentsRequest(RPCRequest, AttachmentsRequest):
    def __init__(self, *args, **kw):
        """Construct an attachments request."""
        super().__init__(method='Bug.attachments', *args, **kw)


@req_cmd(Bugzilla4_4Rpc)
class _GetItemRequest(RPCRequest, GetItemRequest):
    def __init__(self, *args, **kw):
        """Construct a get request."""
        super().__init__(method='Bug.get', *args, **kw)
        # return array of faults for bad bugs instead of directly failing out
        self.params['permissive'] = True


@req_cmd(Bugzilla4_4Rpc, cmd='modify', obj_args=True)
class _ModifyRequest(RPCRequest, ModifyRequest):
    def __init__(self, *args, **kw):
        """Construct a modify request."""
        super().__init__(method='Bug.update', *args, **kw)


@req_cmd(Bugzilla4_4Rpc, cmd='attach', obj_args=True)
class _AttachRequest(RPCRequest, AttachRequest):
    def __init__(self, *args, **kw):
        """Construct an attach request."""
        super().__init__(method='Bug.add_attachment', *args, **kw)


@req_cmd(Bugzilla4_4Rpc, cmd='create', obj_args=True)
class _CreateRequest(RPCRequest, CreateRequest):
    def __init__(self, *args, **kw):
        """Construct a create request."""
        super().__init__(method='Bug.create', *args, **kw)
