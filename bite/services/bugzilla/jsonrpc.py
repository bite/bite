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
        super(IterSearchRequest, self).__init__(*args, **kw)

    def parse(self, data, *args, **kw):
        bugs = ijson.items(data, 'result.bugs.item')
        bugs = (self.bug(service=self, bug=x) for x in bugs)
        return bugs


class BugzillaJsonrpc(Bugzilla):
    #def search(self, *args, **kw):
    #    return IterSearchRequest(self, *args, **kw)

    def __init__(self, **kw):
        url = urlparse(kw['base'])
        path = url.path.rpartition('/')[0]
        url = (url.scheme, url.netloc, path + '/jsonrpc.cgi', None, None, None)
        kw['base'] = urlunparse(url)
        self.headers = {'Accept': 'application/json', 'Content-Type': 'application/json'}
        super(BugzillaJsonrpc, self).__init__(**kw)

    def create_request(self, method, params=None):
        """Construct and return a request object."""
        cookies = []

        if method in ('Bug.update', 'Bug.create'):
            if isinstance(self.auth_token, str):
                params['token'] = self.auth_token
            else:
                cookies = self.auth_token

        args = {}
        args['method'] = method
        args['params'] = [params]
        args['id'] = '0'

        req = Request(method='POST', url=self.base, headers=self.headers,
                      data=json.dumps(args), cookies=cookies)
        return req.prepare()

    #def request(self, method, params=None, iter_content=False):
    #    # temporary compatibility shim
    #    req = self.create_request(method, params)
    #    return self.send(req)

    def send(self, req):
        data = super(BugzillaJsonrpc, self).send(req).json()
        if data['error'] is None:
            return data['result']
        else:
            if data['error']['code'] == 32000 and self.base.startswith('http:'):
                # Bugzilla strangely returns an error under http but works fine under https
                raise RequestError('Received error reply, try using an https:// url instead')
            raise RequestError(msg=data['error']['message'],
                               code=data['error']['code'])

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
