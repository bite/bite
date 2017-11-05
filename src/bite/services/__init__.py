from concurrent.futures import ThreadPoolExecutor
import os
import stat
from urllib.parse import urlparse, urlunparse

import requests
from snakeoil.sequences import iflatten_instance

from .. import __version__, const
from ..cache import Cache
from ..exceptions import RequestError, AuthError, BiteError


def command(cmd_name, service_cls):
    """Register service command function."""
    def wrapped(cls, *args, **kwds):
        send = getattr(service_cls, 'send')
        send_func = lambda self, *args, **kw: send(self, reqs=cls(self, *args, **kw))
        setattr(service_cls, cmd_name, send_func)
        return cls
    return wrapped


def request(service_cls):
    """Register request creation function."""
    def wrapped(cls, *args, **kwds):
        req_func = lambda self, *args, **kw: cls(self, *args, **kw)
        setattr(service_cls, cls.__name__, req_func)
        return cls
    return wrapped


class Request(object):
    """Construct a request."""

    def __init__(self, service, url=None, method=None, params=None, reqs=None):
        self.service = service
        self.options = []

        if url is None:
            url = self.service._base
        _requests = []

        if method is not None:
            req = requests.Request(method='POST', url=url)

            if not self.service.skip_auth and self.service.auth_token is not None:
                req, params = self.service.inject_auth(req, params)
            req.data = self.service._encode_request(method, params)
            _requests.append(req)

        if reqs is not None:
            _requests.extend(reqs)

        self._requests = tuple(_requests)

    def prepare(self):
        reqs = []
        for r in self._requests:
            if isinstance(r, Request):
                reqs.extend(r.prepare())
            elif r is None:
                reqs.append(r)
            else:
                reqs.append(self.service.prepare_request(r))
        return tuple(reqs)

    @staticmethod
    def _http_req_str(req):
        return '{}\n{}\n\n{}'.format(
            req.method + ' ' + req.url,
            '\n'.join('{}: {}'.format(k, v) for k, v in req.headers.items()),
            req.body,
        )

    def __str__(self):
        reqs = []
        for r in self.prepare():
            if r is not None:
                reqs.append(self._http_req_str(r))
        return '\n\n'.join(reqs)

    def parse(self, data):
        return data

    def handle_exception(self, e):
        raise e

    def __len__(self):
        return len(self._requests)

    def __iter__(self):
        return iter(self._requests)


class NullRequest(Request):

    def __init__(self):
        self._requests = (None,)

    def __bool__(self):
        return False


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
    def _encode_request(method, params=None):
        """Encode the data body for a request."""
        raise NotImplementedError()

    @staticmethod
    def _decode_request(request):
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

        request.data = self._encode_request(method, params)
        return self.session.prepare_request(request)

    def parse_response(self, response):
        """Parse the returned response."""
        raise NotImplementedError()

    def prepare_request(self, req):
        return self.session.prepare_request(req)

    def send(self, req):
        """Send request(s) and return a response."""
        reqs = getattr(req, '_requests', req)
        req_parse = getattr(req, 'parse', lambda x: x)

        jobs = []
        for req in iflatten_instance(reqs, Request):
            parse = getattr(req, 'parse', lambda x: x)
            for r in iflatten_instance(req, requests.Request):
                jobs.append((parse, self.executor.submit(self._http_send, r)))

        data = (parse(job.result()) for parse, job in jobs)

        if len(jobs) == 1:
            return req_parse(next(data))
        return req_parse(data)

    def _http_send(self, req):
        """Send an HTTP request and return the parsed response."""
        if req is None:
            return

        try:
            response = self.session.send(
                self.prepare_request(req), stream=True, timeout=self.timeout, verify=self.verify, allow_redirects=False)
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
