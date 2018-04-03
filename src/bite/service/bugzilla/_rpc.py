import base64
import codecs
from itertools import groupby
import os

from . import (
    Bugzilla, BugzillaComment, BugzillaEvent,
    SearchRequest, HistoryRequest, CommentsRequest, AttachmentsRequest,
    GetItemRequest, GetRequest, ModifyRequest,
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
class _AttachRequest(RPCRequest):
    def __init__(self, service, ids, data=None, filepath=None, filename=None, mimetype=None,
                 is_patch=False, is_private=False, comment=None, summary=None, **kw):
        """Add an attachment to a bug

        :param ids: The ids or aliases of bugs that you want to add the attachment to.
        :type ids: list of ints and/or strings
        :param data: Raw attachment data
        :type data: binary data
        :param filepath: Path to the file.
        :type filepath: string
        :param filename: The file name that will be displayed in the UI for the attachment.
        :type filename: string
        :param mimetype: The MIME type of the attachment, like text/plain or image/png.
        :type mimetype: string
        :param comment: A comment to add along with the attachment.
        :type comment: string
        :param summary: A short string describing the attachment.
        :type summary: string
        :param is_patch: True if Bugzilla should treat this attachment as a patch.
            If specified, a content_type doesn't need to be specified as it is forced to text/plain.
            Defaults to false if unspecified.
        :type is_patch: boolean
        :param is_private: True if the attachment should be private, False if public.
            Defaults to false if unspecified.
        :type is_private: boolean

        :raises ValueError: if no bug IDs are specified
        :raises ValueError: if data or filepath arguments aren't specified
        :raises ValueError: if data isn't defined and filepath points to a nonexistent file
        :raises ValueError: if filepath isn't defined and summary or filename isn't specified

        :returns: attachment IDs created
        :rtype: list of attachment IDs
        """
        if not ids:
            raise ValueError('No bug ID(s) or aliases specified')

        params = {'ids': ids}

        if data is not None:
            params['data'] = base64.b64encode(data)
        else:
            if filepath is None:
                raise ValueError('Either data or a filepath must be passed as an argument')
            else:
                if not os.path.exists(filepath):
                    raise ValueError(f'File not found: {filepath}')
                else:
                    with open(filepath, 'rb') as f:
                        params['data'] = base64.b64encode(f.read())

        if filename is None:
            if filepath is not None:
                filename = os.path.basename(filepath)
            else:
                raise ValueError('A valid filename must be specified')

        if mimetype is None and not is_patch:
            if data is not None:
                mimetype = magic.from_buffer(data, mime=True)
            else:
                mimetype = magic.from_file(filepath, mime=True)

        if summary is None:
            if filepath is not None:
                summary = filename
            else:
                raise ValueError('A valid summary must be specified')

        params['file_name'] = filename
        params['summary'] = summary
        if not is_patch:
            params['content_type'] = mimetype
        params['comment'] = comment
        params['is_patch'] = is_patch

        super().__init__(service=service, command='Bug.add_attachment', params=params)

    def parse(self, data):
        return data['attachments']
