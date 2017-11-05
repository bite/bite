from concurrent.futures import ThreadPoolExecutor
import os
import stat
from urllib.parse import urlparse, urlunparse

import requests

from .. import __version__, const
from ..cache import Cache
from ..exceptions import RequestError, AuthError, BiteError


def command(cmd_name, service_cls):
    """Register related service command and request creation functions."""
    def wrapped(cls, *args, **kwds):
        send = getattr(service_cls, 'send')
        send_func = lambda self, *args, **kw: send(self, reqs=cls(self, *args, **kw))
        req_func = lambda self, *args, **kw: cls(self, *args, **kw)
        setattr(service_cls, cmd_name, send_func)
        setattr(service_cls, cls.__name__, req_func)
        return cls
    return wrapped


class Request(object):

    def __init__(self, service):
        self.service = service
        self.requests = []
        self.options = []

    @staticmethod
    def http_req_str(req):
        return '{}\n{}\n\n{}'.format(
            req.method + ' ' + req.url,
            '\n'.join('{}: {}'.format(k, v) for k, v in req.headers.items()),
            req.body,
        )

    def __str__(self):
        requests = []
        for req in self.requests:
            if isinstance(req, Request):
                requests.extend(req.requests)
            else:
                requests.append(req)

        raw_requests = []
        for req in requests:
            raw_requests.append(self.http_req_str(req))

        return '\n\n'.join(raw_requests)

    def parse(self, data):
        return data

    def handle_exception(self, e):
        raise e

    def __len__(self):
        return len(self.requests)

    def __iter__(self):
        return iter(self.requests)


class NullRequest(Request):

    def __init__(self):
        super().__init__(service=None)


class Service(object):

    service_name = None 

    def __init__(self, base, connection=None, verify=True, user=None, password=None, skip_auth=True,
                 auth_token=None, suffix=None, timeout=None, auth_file=None, concurrent=None,
                 cache_cls=None, endpoint='', **kw):
        self.base = base
        self.user = user
        self.password = password
        self.suffix = suffix
        self.verify = verify
        self.timeout = timeout if timeout is not None else 30

        # max workers defaults to system CPU count * 5 if concurrent is None
        self.executor = ThreadPoolExecutor(max_workers=concurrent)

        if cache_cls is None:
            cache_cls = Cache

        url = urlparse(self.base)
        self._base = urlunparse((
            url.scheme,
            url.netloc,
            url.path.rstrip('/') + endpoint,
            None, None, None))

        self.item = 'issue'
        self.item_web_endpoint = None

        cache_name = connection
        if cache_name is None:
            url = urlparse(self.base)
            if len(url.path) <= 1:
                cache_name = url.netloc
            else:
                cache_name = '{}{}'.format(url.netloc, url.path.rstrip('/').replace('/', '-'))
            if url.username is not None or url.password is not None:
                cache_name = cache_name.split('@', 1)[1]
        self.cache = cache_cls(cache_name)

        self.skip_auth = skip_auth
        self.auth_token = auth_token
        if auth_file is None:
            self.auth_file = os.path.join(const.USER_CACHE_PATH, 'auth', cache_name)
        else:
            self.auth_file = auth_file

        # block when urllib3 connection pool is full
        s = requests.Session()
        a = requests.adapters.HTTPAdapter(pool_block=True)
        s.mount('https://', a)
        s.mount('http://', a)
        self.session = s

        self.session.headers['User-Agent'] = '{}-{}'.format('bite', __version__)
        self.session.headers['Accept-Encoding'] = ', '.join(('gzip', 'deflate', 'compress'))

    @property
    def cache_updates(self):
        """Pull latest data from service for cache update."""
        return {}

    def login(self, user=None, password=None):
        """Authenticate a session."""
        if user is None:
            user = self.user
        if password is None:
            password = self.password

        if user is None or password is None:
            raise ValueError('Both user and password parameters must be specified')

    def cache_auth_token(self):
        try:
            os.makedirs(os.path.dirname(self.auth_file))
        except FileExistsError:
            pass

        try:
            with open(self.auth_file, 'w+') as f:
                os.chmod(self.auth_file, stat.S_IREAD | stat.S_IWRITE)
                f.write(self.auth_token)
        except (PermissionError, IsADirectoryError) as e:
            raise BiteError('failed caching auth token to {!r}: {}'.format(
                self.auth_file, e.strerror))

    def load_auth_token(self):
        try:
            with open(self.auth_file, 'r') as f:
                self.auth_token = f.read()
        except IOError:
            return None

    def remove_auth_token(self):
        """Remove an authentication token."""
        try:
            os.remove(self.auth_file)
        except FileExistsError:
            pass
        self.auth_token = None

    def __str__(self):
        return str(self.base)

    @staticmethod
    def encode_request(method, params=None):
        """Encode the data body for a request."""
        raise NotImplementedError()

    @staticmethod
    def decode_request(request):
        """Decode the data body of a request."""
        raise NotImplementedError()

    def inject_auth(self, request, params):
        """Add authentication data to a request."""
        return request, params

    def create_request(self, url=None, method=None, params=None):
        """Construct a request."""
        if url is None:
            url = self._base

        request = requests.Request(method='POST', url=url)

        if not self.skip_auth and self.auth_token is not None:
            request, params = self.inject_auth(request, params)

        request.data = self.encode_request(method, params)
        return self.session.prepare_request(request)

    def parse_response(self, response):
        """Parse the returned response."""
        raise NotImplementedError()

    def send(self, reqs, raw=False):
        """Send request(s) and return a response."""
        if not raw and isinstance(reqs, Request):
            parse = reqs.parse
        else:
            parse = lambda x: x

        try:
            if len(reqs) == 0:
                return
            elif len(reqs) > 1:
                return parse(self._parallel_send(reqs))
        except TypeError:
            pass

        if isinstance(reqs, Request):
            req = reqs.requests[0]
            handle_exception = reqs.handle_exception
        else:
            req = reqs
            def _raise(e): raise
            handle_exception = _raise

        try:
            data = self._http_send(req)
        except RequestError as e:
            handle_exception(e)

        return parse(data)

    def _http_send(self, req):
        """Send an HTTP request and return the parsed response."""
        try:
            response = self.session.send(
                req, stream=True, timeout=self.timeout, verify=self.verify, allow_redirects=False)
        except requests.exceptions.SSLError as e:
            raise RequestError('SSL certificate verification failed')
        except requests.exceptions.ConnectionError as e:
            raise RequestError('failed to establish connection')
        except requests.exceptions.ReadTimeout as e:
            raise RequestError('request timed out')

        if response.status_code == 301:
            old = self.base
            new = response.headers['Location']
            raise RequestError('service moved permanently: {} -> {}'.format(old, new))

        if response.ok:
            return self.parse_response(response)
        else:
            if response.status_code in (401, 403):
                raise AuthError('Authentication failed')
            else:
                try:
                    raise response.raise_for_status()
                except requests.exceptions.HTTPError:
                    raise RequestError('HTTP Error {}: {}'.format(
                        response.status_code, response.reason.lower()), text=response.text)

    def _parallel_send(self, reqs, block=True):
        """Run parallel requests at once."""
        jobs = []
        for req in reqs:
            if isinstance(req, tuple) or isinstance(req, list):
                yield self._parallel_send(req)
            else:
                jobs.append(self.executor.submit(self.send, req))

        for job in jobs:
            yield job.result()

    def _desuffix(self, s):
        if self.suffix is not None:
            index = s.find(self.suffix)
            if index != -1:
                s = s[:index]
        return s

    def _resuffix(self, s):
        if self.suffix is not None and '@' not in s:
            s = s + self.suffix
        return s

    def substitute_aliases(self, field):
        try:
            return self.attribute_aliases[field]
        except KeyError:
            return field
