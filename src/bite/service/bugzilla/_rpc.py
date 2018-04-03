from itertools import groupby

from . import (
    Bugzilla, BugzillaComment, BugzillaEvent,
    SearchRequest, HistoryRequest, CommentsRequest, AttachmentsRequest,
    GetItemRequest, GetRequest, ModifyRequest, AttachRequest,
    ExtensionsRequest, VersionRequest, FieldsRequest, ProductsRequest, UsersRequest)
from .. import Request, RPCRequest, req_cmd
from ... import const, magic
from ...exceptions import BiteError


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


@req_cmd(BugzillaRpc, 'create')
class _CreateRequest(RPCRequest):
    def __init__(self, service, product, component, version, summary, description=None, op_sys=None,
                 platform=None, priority=None, severity=None, alias=None, assigned_to=None,
                 cc=None, target_milestone=None, groups=None, status=None, **kw):
        """Create a new bug given a list of parameters

        :returns: ID of the newly created bug
        :rtype: int
        """
        params = {}
        params['product'] = product
        params['component'] = component
        params['version'] = version
        params['summary'] = summary
        if description is not None:
            params['description'] = description
        if op_sys is not None:
            params['op_sys'] = op_sys
        if platform is not None:
            params['platform'] = platform
        if priority is not None:
            params['priority'] = priority
        if severity is not None:
            params['severity'] = severity
        if alias is not None:
            params['alias'] = alias
        if assigned_to is not None:
            params['assigned_to'] = assigned_to
        if cc is not None:
            params['cc'] = cc
        if target_milestone is not None:
            params['target_milestone'] = target_milestone
        if groups is not None:
            params['groups'] = groups
        if status is not None:
            params['status'] = status

        super().__init__(service=service, command='Bug.create', params=params)

    def parse(self, data):
        return data['id']


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
