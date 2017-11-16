try: import simplejson as json
except ImportError: import json

from . import BugzillaError
from ._rpc import BugzillaRpc, _SearchRequest as BugzillaSearchRequest
from .._jsonrpc import Jsonrpc
from ...exceptions import AuthError


class BugzillaJsonrpc(BugzillaRpc, Jsonrpc):
    """Support Bugzilla's deprecated JSON-RPC interface."""

    _service = 'bugzilla-jsonrpc'

    def __init__(self, **kw):
        super().__init__(endpoint='/jsonrpc.cgi', **kw)

    def _encode_request(self, method, params):
        """Encode the data body for a JSON-RPC request."""
        return super()._encode_request(method=method, params=params, id=0)

    def parse_response(self, response):
        data = super().parse_response(response)
        error = data.get('error')
        if error is None:
            return data['result']
        else:
            self.handle_error(code=error['code'], msg=error['message'])


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
