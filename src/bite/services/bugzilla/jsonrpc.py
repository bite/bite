from urllib.parse import urlparse, urlunparse

try: import simplejson as json
except ImportError: import json
#import ijson
from requests import Request

from bite.exceptions import AuthError, RequestError
from bite.services.bugzilla import Bugzilla, SearchRequest

class IterSearchRequest(SearchRequest):
    def __init__(self, *args, **kw):
        """Construct a search request."""
        super().__init__(*args, **kw)

    def parse(self, data, *args, **kw):
        bugs = ijson.items(data, 'result.bugs.item')
        bugs = (self.bug(service=self, bug=x) for x in bugs)
        return bugs


class BugzillaJsonrpc(Bugzilla):
    #def search(self, *args, **kw):
    #    return IterSearchRequest(self, *args, **kw)

    def __init__(self, **kw):
        # make sure to use the correct jsonrpc endpoint
        url = urlparse(kw['base'])
        path = url.path.rpartition('/')[0]
        url = (url.scheme, url.netloc, path + '/jsonrpc.cgi', None, None, None)
        self._base = urlunparse(url)

        self.headers = {'Accept': 'application/json', 'Content-Type': 'application/json'}

        super().__init__(**kw)

    def create_request(self, method, params=None):
        """Construct and return a request object."""
        cookies = []

        if self.auth_token is not None:
            if isinstance(self.auth_token, str):
                params['token'] = self.auth_token
            else:
                cookies = self.auth_token

        args = {}
        args['method'] = method
        args['params'] = [params]
        args['id'] = '0'

        req = Request(method='POST', url=self._base, headers=self.headers,
                      data=json.dumps(args), cookies=cookies)
        return req.prepare()

    #def request(self, method, params=None, iter_content=False):
    #    # temporary compatibility shim
    #    req = self.create_request(method, params)
    #    return self.send(req)

    def send(self, req):
        response = super().send(req)

        try:
            data = response.json()
        except json.decoder.JSONDecodeError as e:
            raise RequestError('error decoding response, JSON-RPC interface likely disabled on server')

        if data.get('error') is None:
            return data['result']
        else:
            error = data.get('error')
            if error.get('code') == 32000:
                if self._base.startswith('http:'):
                    # bugzilla strangely returns an error under http but works fine under https
                    raise RequestError('Received error reply, try using an https:// url instead')
                elif 'expired' in error.get('message'):
                    # assume the auth token has expired
                    raise AuthError('auth token expired', expired=True)
            elif error.get('code') == 102:
                raise AuthError('access denied')
            raise RequestError(msg=error.get('message'),
                               code=error.get('code'))

class IterContent(object):
    def __init__(self, file, size=64*1024):
        self.initial = True
        self.chunks = file.iter_content(chunk_size=size)

    def read(self, size=64*1024):
        chunk = next(self.chunks)
        # hacky method of checking the initial chunk for errors
        if self.initial:
            self.initial = False
            if not chunk.startswith(b'{"error":null,'):
                error = json.loads(str(chunk))['error']
                if error['code'] == 102:
                    raise AuthError(msg=error['message'], code=error['code'])
                else:
                    raise RequestError(msg=error['message'], code=error['code'])
        return chunk
