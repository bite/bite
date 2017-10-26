try: import simplejson as json
except ImportError: import json

from . import Bugzilla, SearchRequest
from ...exceptions import AuthError, RequestError


class BugzillaJsonrpc(Bugzilla):
    """Support Bugzilla's deprecated JSON-RPC interface."""

    def __init__(self, **kw):
        self.endpoint = '/jsonrpc.cgi'
        super().__init__(**kw)
        self.session.headers.update({
            'Accept': 'application/json',
            'Content-Type': 'application/json'
        })

    def encode_request(self, method, params):
        """Encode the data body for a JSON-RPC request."""
        return json.dumps({'method': method, 'params': [params], 'id': 0})

    def parse_response(self, response):
        try:
            data = response.json()
        except json.decoder.JSONDecodeError as e:
            raise RequestError('error decoding response, JSON-RPC interface likely disabled on server')

        if data.get('error') is None:
            return data['result']
        else:
            self.handle_error(data.get('error'))

    @staticmethod
    def handle_error(error):
        if error.get('code') == 32000:
            if 'expired' in error.get('message'):
                # assume the auth token has expired
                raise AuthError('auth token expired', expired=True)
        elif error.get('code') == 102:
            raise AuthError('access denied')
        raise RequestError(msg=error.get('message'), code=error.get('code'))


class _StreamingBugzillaJsonrpc(BugzillaJsonrpc):

    def search(self, *args, **kw):
       return _IterSearchRequest(self, *args, **kw)

    def parse_response(self, response):
        return _IterContent(response)


class _IterSearchRequest(SearchRequest):

    def __init__(self, *args, **kw):
        """Construct a search request."""
        super().__init__(*args, **kw)

    def parse(self, data, *args, **kw):
        import ijson.backends.yajl2 as ijson
        bugs = ijson.items(data, 'result.bugs.item')
        return (self.service.bug(service=self.service, bug=bug) for bug in bugs)


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
                BugzillaJsonrpc.handle_error(error)
        return chunk
