from snakeoil.demandload import demandload

from . import (
    Bugzilla,
    SearchRequest, HistoryRequest, CommentsRequest, AttachmentsRequest, LoginRequest,
    GetItemRequest, GetRequest, ModifyRequest, AttachRequest, CreateRequest,
    ExtensionsRequest, VersionRequest, FieldsRequest, ProductsRequest, UsersRequest)
from .. import RPCRequest, req_cmd

demandload('bite:const')


class BugzillaRpc(Bugzilla):
    pass


@req_cmd(BugzillaRpc)
class _LoginRequest(RPCRequest):
    def __init__(self, user, password, service, restrict_login=False):
        """Log in as a user and get an auth token."""
        params = {
            'login': user,
            'password': password,
            'restrict_login': restrict_login,
        }
        super().__init__(service=service, command='User.login', params=params)

    def parse(self, data):
        return data['token']


@req_cmd(BugzillaRpc, 'users')
class _UsersRequest(UsersRequest, RPCRequest):
    def __init__(self, *args, **kw):
        super().__init__(command='User.get', *args, **kw)


@req_cmd(BugzillaRpc, 'fields')
class _FieldsRequest(FieldsRequest, RPCRequest):
    def __init__(self, *args, **kw):
        super().__init__(command='Bug.fields', *args, **kw)


@req_cmd(BugzillaRpc, 'products')
class _ProductsRequest(ProductsRequest, RPCRequest):
    def __init__(self, *args, **kw):
        super().__init__(command='Product.get', *args, **kw)


@req_cmd(BugzillaRpc, 'extensions')
class _ExtensionsRequest(ExtensionsRequest, RPCRequest):
    def __init__(self, *args, **kw):
        """Construct an extensions request."""
        super().__init__(command='Bugzilla.extensions', *args, **kw)


@req_cmd(BugzillaRpc, 'version')
class _VersionRequest(VersionRequest, RPCRequest):
    def __init__(self, *args, **kw):
        """Construct a version request."""
        super().__init__(command='Bugzilla.version', *args, **kw)


@req_cmd(BugzillaRpc, 'get')
class _GetRequest(GetRequest):
    def __init__(self, *args, **kw):
        """Construct a get request."""
        super().__init__(*args, **kw)


@req_cmd(BugzillaRpc, 'search')
class _SearchRequest(SearchRequest, RPCRequest):
    def __init__(self, *args, **kw):
        """Construct a search request."""
        super().__init__(command='Bug.search', *args, **kw)


@req_cmd(BugzillaRpc, 'history')
class _HistoryRequest(HistoryRequest, RPCRequest):
    def __init__(self, *args, **kw):
        """Construct a history request."""
        super().__init__(command='Bug.history', *args, **kw)


@req_cmd(BugzillaRpc, 'comments')
class _CommentsRequest(CommentsRequest, RPCRequest):
    def __init__(self, *args, **kw):
        """Construct a comments request."""
        super().__init__(command='Bug.comments', *args, **kw)


@req_cmd(BugzillaRpc, 'attachments')
class _AttachmentsRequest(AttachmentsRequest, RPCRequest):
    def __init__(self, *args, **kw):
        """Construct an attachments request."""
        super().__init__(command='Bug.attachments', *args, **kw)


@req_cmd(BugzillaRpc)
class _GetItemRequest(GetItemRequest, RPCRequest):
    def __init__(self, *args, **kw):
        """Construct a get request."""
        super().__init__(command='Bug.get', *args, **kw)
        # return array of faults for bad bugs instead of directly failing out
        self.params['permissive'] = True


class ChangesRequest(RPCRequest):
    pass


@req_cmd(BugzillaRpc, 'modify')
class _ModifyRequest(ModifyRequest, RPCRequest):
    def __init__(self, *args, **kw):
        """Construct a modify request."""
        super().__init__(command='Bug.update', *args, **kw)


@req_cmd(BugzillaRpc, 'attach')
class _AttachRequest(AttachRequest, RPCRequest):
    def __init__(self, *args, **kw):
        """Construct an attach request."""
        super().__init__(command='Bug.add_attachment', *args, **kw)


@req_cmd(BugzillaRpc, 'create')
class _CreateRequest(CreateRequest, RPCRequest):
    def __init__(self, *args, **kw):
        """Construct a create request."""
        super().__init__(command='Bug.create', *args, **kw)
