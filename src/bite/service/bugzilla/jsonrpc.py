"""Support Bugzilla's deprecated JSON-RPC interface.

API docs: https://www.bugzilla.org/docs/4.4/en/html/api/Bugzilla/WebService/Server/JSONRPC.html
"""

try: import simplejson as json
except ImportError: import json

from ._rpc import Bugzilla4_4Rpc, Bugzilla5_0Rpc, _SearchRequest5_0 as BugzillaSearchRequest
from .._jsonrpc import Jsonrpc


class _BugzillaJsonrpcBase(Jsonrpc):
    """Base service class for Bugzilla JSON-RPC interface."""

    def __init__(self, **kw):
        super().__init__(endpoint='/jsonrpc.cgi', **kw)

    def handle_error(error):
        super().handle_error(code=error['code'], msg=error['message'])


class Bugzilla4_4Jsonrpc(_BugzillaJsonrpcBase, Bugzilla4_4Rpc):
    """Service for Bugzilla 4.4 JSON-RPC interface."""

    _service = 'bugzilla4.4-jsonrpc'


class Bugzilla5_0Jsonrpc(_BugzillaJsonrpcBase, Bugzilla5_0Rpc):
    """Service for Bugzilla 5.0 JSON-RPC interface."""

    _service = 'bugzilla5.0-jsonrpc'


class BugzillaJsonrpc(_BugzillaJsonrpcBase, Bugzilla5_0Rpc):
    """Service for Bugzilla latest JSON-RPC interface."""

    _service = 'bugzilla-jsonrpc'


class _StreamingBugzillaJsonrpc(BugzillaJsonrpc):

    _service = None

    def parse_response(self, response):
        return self._IterContent(response)

    class SearchRequest(BugzillaSearchRequest):

        def __init__(self, *args, **kw):
            """Construct a search request."""
            super().__init__(*args, **kw)

        def parse(self, data, *args, **kw):
            import ijson.backends.yajl2 as ijson
            bugs = ijson.items(data, 'result.bugs.item')
            return (self.service.item(service=self.service, bug=bug) for bug in bugs)

    class _IterContent(object):

        def __init__(self, file, size=64*1024):
            self.initial = True
            self.chunks = file.iter_content(chunk_size=size)

        def read(self, size=64*1024):
            chunk = next(self.chunks)
            # check the initial chunk for errors
            if self.initial:
                self.initial = False
                try:
                    error = json.loads(chunk)['error']
                except json.decoder.JSONDecodeError as e:
                    # if we can't load it, assume it's a valid json doc chunk
                    return chunk
                if error is not None:
                    super().handle_error(error)
            return chunk
