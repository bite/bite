from . import Bugzilla, Bugzilla5_0, Bugzilla5_2
from .reqs import (
    SearchRequest4_4, SearchRequest5_0, ChangesRequest, CommentsRequest,
    AttachmentsRequest, LoginRequest, GetItemRequest, ModifyRequest,
    AttachRequest, CreateRequest, ExtensionsRequest, VersionRequest, FieldsRequest,
    ProductsRequest, UsersRequest,
)
from .._reqs import RPCRequest, GetRequest, req_cmd


class Bugzilla4_4Rpc(Bugzilla):
    """Support bugzilla 4.4 RPC calls."""


class Bugzilla5_0Rpc(Bugzilla5_0, Bugzilla4_4Rpc):
    """Support bugzilla 5.0 RPC calls."""


class Bugzilla5_2Rpc(Bugzilla5_2, Bugzilla5_0Rpc):
    """Support bugzilla 5.2 RPC calls."""


@req_cmd(Bugzilla4_4Rpc)
class _LoginRequest(RPCRequest, LoginRequest):
    def __init__(self, *args, **kw):
        super().__init__(command='User.login', *args, **kw)


@req_cmd(Bugzilla4_4Rpc, 'users')
class _UsersRequest(RPCRequest, UsersRequest):
    def __init__(self, *args, **kw):
        super().__init__(command='User.get', *args, **kw)


@req_cmd(Bugzilla4_4Rpc, 'fields')
class _FieldsRequest(RPCRequest, FieldsRequest):
    def __init__(self, *args, **kw):
        super().__init__(command='Bug.fields', *args, **kw)


@req_cmd(Bugzilla4_4Rpc, 'products')
class _ProductsRequest(RPCRequest, ProductsRequest):
    def __init__(self, *args, **kw):
        super().__init__(command='Product.get', *args, **kw)


@req_cmd(Bugzilla4_4Rpc, 'extensions')
class _ExtensionsRequest(RPCRequest, ExtensionsRequest):
    def __init__(self, *args, **kw):
        """Construct an extensions request."""
        super().__init__(command='Bugzilla.extensions', *args, **kw)


@req_cmd(Bugzilla4_4Rpc, 'version')
class _VersionRequest(RPCRequest, VersionRequest):
    def __init__(self, *args, **kw):
        """Construct a version request."""
        super().__init__(command='Bugzilla.version', *args, **kw)


@req_cmd(Bugzilla4_4Rpc, 'get')
class _GetRequest(GetRequest):
    def __init__(self, *args, **kw):
        """Construct a get request."""
        super().__init__(*args, **kw)


@req_cmd(Bugzilla4_4Rpc, 'search')
class _SearchRequest4_4(RPCRequest, SearchRequest4_4):
    def __init__(self, *args, **kw):
        """Construct a search request."""
        super().__init__(command='Bug.search', *args, **kw)


@req_cmd(Bugzilla5_0Rpc, 'search')
class _SearchRequest5_0(RPCRequest, SearchRequest5_0):
    def __init__(self, *args, **kw):
        """Construct a search request."""
        super().__init__(command='Bug.search', *args, **kw)


@req_cmd(Bugzilla4_4Rpc, 'changes')
class _ChangesRequest(RPCRequest, ChangesRequest):
    def __init__(self, *args, **kw):
        """Construct a changes request."""
        super().__init__(command='Bug.history', *args, **kw)


@req_cmd(Bugzilla4_4Rpc, 'comments')
class _CommentsRequest(RPCRequest, CommentsRequest):
    def __init__(self, *args, **kw):
        """Construct a comments request."""
        super().__init__(command='Bug.comments', *args, **kw)


@req_cmd(Bugzilla4_4Rpc, 'attachments')
class _AttachmentsRequest(RPCRequest, AttachmentsRequest):
    def __init__(self, *args, **kw):
        """Construct an attachments request."""
        super().__init__(command='Bug.attachments', *args, **kw)


@req_cmd(Bugzilla4_4Rpc)
class _GetItemRequest(RPCRequest, GetItemRequest):
    def __init__(self, *args, **kw):
        """Construct a get request."""
        super().__init__(command='Bug.get', *args, **kw)
        # return array of faults for bad bugs instead of directly failing out
        self.params['permissive'] = True


@req_cmd(Bugzilla4_4Rpc, 'modify')
class _ModifyRequest(RPCRequest, ModifyRequest):
    def __init__(self, *args, **kw):
        """Construct a modify request."""
        super().__init__(command='Bug.update', *args, **kw)


@req_cmd(Bugzilla4_4Rpc, 'attach')
class _AttachRequest(RPCRequest, AttachRequest):
    def __init__(self, *args, **kw):
        """Construct an attach request."""
        super().__init__(command='Bug.add_attachment', *args, **kw)


@req_cmd(Bugzilla4_4Rpc, 'create')
class _CreateRequest(RPCRequest, CreateRequest):
    def __init__(self, *args, **kw):
        """Construct a create request."""
        super().__init__(command='Bug.create', *args, **kw)
