from concurrent.futures import ThreadPoolExecutor
import os
import types
from urllib.parse import urlparse, urlunparse, urlencode

import requests
from snakeoil.sequences import iflatten_instance

from .. import __title__, __version__
from ..cache import Cache, Auth
from ..exceptions import RequestError, AuthError, BiteError


def command(cmd_name, service_cls):
    """Register service command function."""
    def wrapped(cls, *args, **kwds):
        send = getattr(service_cls, 'send')
        send_func = lambda self, *args, **kw: send(self, req=cls(*args, service=self, **kw))
        setattr(service_cls, cmd_name, send_func)
        return cls
    return wrapped


def request(service_cls):
    """Register request creation function."""
    def wrapped(cls, *args, **kwds):
        req_func = lambda self, *args, **kw: cls(*args, service=self, **kw)
        setattr(service_cls, cls.__name__.lstrip('_'), req_func)
        return cls
    return wrapped


class Request(object):
    """Construct a request."""

    def __init__(self, service, url=None, method=None, params=None, reqs=None):
        self.service = service
        self.options = []
        self.params = params
        self._req = None

        if method is not None:
            if url is None:
                url = self.service._base
            self._req = requests.Request(method=method, url=url)

        self._reqs = tuple(reqs) if reqs is not None else ()

    @property
    def _requests(self):
        if self._req is not None:
            yield self._finalize(self._req, self.params)
        yield from self._reqs

    def _finalize(self, req, params):
        if not (self.service.skip_auth or self.service.authenticated) and self.service.auth:
            req, self.params = self.service.inject_auth(req, self.params)
        return req

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

    def __iter__(self):
        return self._requests


class RPCRequest(Request):
    """Construct an RPC request."""

    def __init__(self, command, **kw):
        self.command = command
        super().__init__(method='POST', **kw)

    def _finalize(self, req, params):
        req = super()._finalize(req, params)
        req.data = self.service._encode_request(self.command, self.params)
        return req


class RESTRequest(Request):
    """Construct a REST request."""

    def __init__(self, endpoint, method='GET', **kw):
        self.endpoint = endpoint
        super().__init__(method=method, **kw)

    def _finalize(self, req, params):
        req = super()._finalize(req, params)
        params = '?' + urlencode(self.params) if self.params else ''
        req.url = '{}/{}{}'.format(req.url, self.endpoint.lstrip('/'), params)
        return req


class NullRequest(Request):

    def __init__(self, generator=False):
        super().__init__(service=None)
        self._generator = generator

    def __bool__(self):
        return False

    def parse(self, data):
        if not self._generator:
            return None

        while True:
            yield None


class Service(object):

    _service = None

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
        self.concurrent = self.executor._max_workers

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
        self.authenticated = False
        self.auth = Auth(cache_name, path=auth_file, token=auth_token, autoload=(not skip_auth))

        # block when urllib3 connection pool is full
        s = requests.Session()
        a = requests.adapters.HTTPAdapter(pool_maxsize=self.concurrent, pool_block=True)
        s.mount('https://', a)
        s.mount('http://', a)
        self.session = s

        self.session.headers['User-Agent'] = '{}-{}'.format(__title__, __version__)
        self.session.headers['Accept-Encoding'] = ', '.join(('gzip', 'deflate', 'compress'))

    @property
    def cache_updates(self):
        """Pull latest data from service for cache update."""
        return {}

    def login(self, user=None, password=None, **kw):
        """Authenticate a session."""
        if not self.auth:
            if user is None:
                user = self.user
            if password is None:
                password = self.password

            if user is None or password is None:
                raise BiteError('Both user and password parameters must be specified')

            token = self._get_auth_token(user, password, **kw)
            self.auth.update(token)

    def _get_auth_token(self, user=None, password=None, **kw):
        """Get an authentication token from the service."""
        return self.send(self.LoginRequest(user=user, password=password, **kw))

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

    def inject_auth(self, request=None, params=None):
        """Authenticate a request or session."""
        return request, params

    def create_request(self, url=None, method=None, params=None):
        """Construct a request."""
        if url is None:
            url = self._base

        request = requests.Request(method='POST', url=url)

        if not (self.skip_auth or self.authenticated) and self.auth:
            request, params = self.inject_auth(request, params)

        request.data = self._encode_request(method, params)
        return self.session.prepare_request(request)

    def parse_response(self, response):
        """Parse the returned response."""
        raise NotImplementedError()

    def prepare_request(self, req):
        return self.session.prepare_request(req)

    def send(self, req):
        """Send request(s) and return parsed response data."""
        def _raise(e): raise
        ident = lambda x: x
        req_parse = getattr(req, 'parse', ident)
        req_handle_exception = getattr(req, 'handle_exception', _raise)

        jobs = []
        for subreq in iflatten_instance(iter(req), Request):
            parse = getattr(subreq, 'parse', ident)
            handle_exception = getattr(subreq, 'handle_exception', _raise)
            http_reqs = [
                self.executor.submit(self._http_send, x) for x in
                iflatten_instance(subreq, requests.Request)]
            jobs.append((parse, handle_exception, http_reqs))

        def _send_subreqs(jobs):
            for parse, handle_exception, http_reqs in jobs:
                results = None
                try:
                    if len(http_reqs) == 1:
                        results = http_reqs[0].result()
                    elif len(http_reqs) > 1:
                        results = (x.result() for x in http_reqs)
                    yield parse(results)
                except RequestError as e:
                    handle_exception(e)

        data = _send_subreqs(jobs)
        if len(jobs) == 1 and isinstance(req, Request):
            try:
                while isinstance(data, types.GeneratorType):
                    data = next(data)
            except RequestError as e:
                req_handle_exception(e)
        return req_parse(data)

    def _http_send(self, req):
        """Send an HTTP request and return the parsed response."""
        try:
            response = self.session.send(
                self.prepare_request(req), stream=True, timeout=self.timeout,
                verify=self.verify, allow_redirects=False)
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
            self._failed_http_response(response)

    def _failed_http_response(self, response):
        if response.status_code in (401, 403):
            raise AuthError('authentication failed')
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
