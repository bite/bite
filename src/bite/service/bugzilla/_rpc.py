from snakeoil.demandload import demandload

from . import (
    Bugzilla, SearchRequest4_4, SearchRequest5_0, HistoryRequest, CommentsRequest,
    AttachmentsRequest, LoginRequest, GetItemRequest, GetRequest, ModifyRequest,
    AttachRequest, CreateRequest, ExtensionsRequest, VersionRequest, FieldsRequest,
    ProductsRequest, UsersRequest)
from .. import RPCRequest, req_cmd

demandload('bite:const')


class Bugzilla4_4Rpc(Bugzilla):
    """Support bugzilla 4.4 RPC calls."""


class Bugzilla5_0Rpc(Bugzilla4_4Rpc):
    """Support bugzilla 5.0 RPC calls."""


class BugzillaRpc(Bugzilla5_0Rpc):
    """Support bugzilla latest RPC calls."""


@req_cmd(Bugzilla4_4Rpc)
class _LoginRequest(LoginRequest, RPCRequest):
    def __init__(self, *args, **kw):
        super().__init__(command='User.login', *args, **kw)


@req_cmd(Bugzilla4_4Rpc, 'users')
class _UsersRequest(UsersRequest, RPCRequest):
    def __init__(self, *args, **kw):
        super().__init__(command='User.get', *args, **kw)


@req_cmd(Bugzilla4_4Rpc, 'fields')
class _FieldsRequest(FieldsRequest, RPCRequest):
    def __init__(self, *args, **kw):
        super().__init__(command='Bug.fields', *args, **kw)


@req_cmd(Bugzilla4_4Rpc, 'products')
class _ProductsRequest(ProductsRequest, RPCRequest):
    def __init__(self, *args, **kw):
        super().__init__(command='Product.get', *args, **kw)


@req_cmd(Bugzilla4_4Rpc, 'extensions')
class _ExtensionsRequest(ExtensionsRequest, RPCRequest):
    def __init__(self, *args, **kw):
        """Construct an extensions request."""
        super().__init__(command='Bugzilla.extensions', *args, **kw)


@req_cmd(Bugzilla4_4Rpc, 'version')
class _VersionRequest(VersionRequest, RPCRequest):
    def __init__(self, *args, **kw):
        """Construct a version request."""
        super().__init__(command='Bugzilla.version', *args, **kw)


@req_cmd(Bugzilla4_4Rpc, 'get')
class _GetRequest(GetRequest):
    def __init__(self, *args, **kw):
        """Construct a get request."""
        super().__init__(*args, **kw)


@req_cmd(Bugzilla4_4Rpc, 'search')
class _SearchRequest4_4(SearchRequest4_4, RPCRequest):
    def __init__(self, *args, **kw):
        """Construct a search request."""
        super().__init__(command='Bug.search', *args, **kw)


@req_cmd(Bugzilla5_0Rpc, 'search')
class _SearchRequest5_0(SearchRequest5_0, RPCRequest):
    def __init__(self, *args, **kw):
        """Construct a search request."""
        super().__init__(command='Bug.search', *args, **kw)


@req_cmd(Bugzilla4_4Rpc, 'history')
class _HistoryRequest(HistoryRequest, RPCRequest):
    def __init__(self, *args, **kw):
        """Construct a history request."""
        super().__init__(command='Bug.history', *args, **kw)


@req_cmd(Bugzilla4_4Rpc, 'comments')
class _CommentsRequest(CommentsRequest, RPCRequest):
    def __init__(self, *args, **kw):
        """Construct a comments request."""
        super().__init__(command='Bug.comments', *args, **kw)


@req_cmd(Bugzilla4_4Rpc, 'attachments')
class _AttachmentsRequest(AttachmentsRequest, RPCRequest):
    def __init__(self, *args, **kw):
        """Construct an attachments request."""
        super().__init__(command='Bug.attachments', *args, **kw)


@req_cmd(Bugzilla4_4Rpc)
class _GetItemRequest(GetItemRequest, RPCRequest):
    def __init__(self, *args, **kw):
        """Construct a get request."""
        super().__init__(command='Bug.get', *args, **kw)
        # return array of faults for bad bugs instead of directly failing out
        self.params['permissive'] = True


class ChangesRequest(RPCRequest):
    pass


@req_cmd(Bugzilla4_4Rpc, 'modify')
class _ModifyRequest(ModifyRequest, RPCRequest):
    def __init__(self, *args, **kw):
        """Construct a modify request."""
        super().__init__(command='Bug.update', *args, **kw)


@req_cmd(Bugzilla4_4Rpc, 'attach')
class _AttachRequest(AttachRequest, RPCRequest):
    def __init__(self, *args, **kw):
        """Construct an attach request."""
        super().__init__(command='Bug.add_attachment', *args, **kw)


@req_cmd(Bugzilla4_4Rpc, 'create')
class _CreateRequest(CreateRequest, RPCRequest):
    def __init__(self, *args, **kw):
        """Construct a create request."""
        super().__init__(command='Bug.create', *args, **kw)
