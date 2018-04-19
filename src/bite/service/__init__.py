from concurrent.futures import ThreadPoolExecutor
from functools import wraps
from urllib.parse import urlparse, urlunparse, urlencode
import re

import requests
from snakeoil.demandload import demandload
from snakeoil.sequences import iflatten_instance

from .. import __title__, __version__
from ..cache import Cache, Auth
from ..exceptions import RequestError, AuthError, BiteError
from ..objects import Item, Attachment

demandload(
    'warnings',
    'urllib3',
)


def req_cmd(service_cls, cmd_name=None):
    """Register service request and command functions."""
    def wrapped(cls, *args, **kwds):
        req_func = lambda self, *args, **kw: cls(*args, service=self, **kw)
        name = re.match(r'^_?([a-zA-Z]+).*$', cls.__name__)
        if not name:
            raise ValueError(f'invalid request name: {cls.__name__!r}')
        setattr(service_cls, name.group(1), req_func)
        if cmd_name is not None:
            send = getattr(service_cls, 'send')
            send_func = lambda self, *args, **kw: send(self, cls(*args, service=self, **kw))
            setattr(service_cls, cmd_name, send_func)
        return cls
    return wrapped


def generator(func):
    """Register request creation function."""
    @wraps(func)
    def wrapped(*args, **kw):
        return func(*args, **kw)
    wrapped.generator = True
    return wrapped


class Request(object):
    """Construct a request."""

    def __init__(self, service, url=None, method=None, params=None, reqs=None, **kw):
        self.service = service
        self.options = []
        self.params = params if params is not None else {}
        self._req = None
        self._finalized = False

        if method is not None:
            if url is None:
                url = self.service._base
            self._req = requests.Request(method=method, url=url)

        self._reqs = tuple(reqs) if reqs is not None else ()

    @property
    def _requests(self):
        if self._req is not None:
            if not self._finalized:
                self._finalize()
            yield self._req
        yield from self._reqs

    def _finalize(self):
        """Finalize a request object for sending.

        For the generic case, authentication data is injected into the request
        if available and required.
        """
        self._finalized = True
        if not self.service.authenticated and self.service.auth:
            self._req, self.params = self.service.inject_auth(self._req, self.params)

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
        """Parse the data returned from a given request."""
        return data

    def send(self):
        """Send a request object to the related service."""
        return self.service.send(self)

    def handle_exception(self, e):
        raise e

    def __len__(self):
        return len(list(self._requests))

    def __iter__(self):
        return self._requests


# TODO: run these asynchronously
class PagedRequest(Request):
    """Keep requesting matching records until all relevant results are returned."""

    def __init__(self, *args, **kw):
        self._offset_key = 'offset'
        super().__init__(*args, **kw)
        # total number of elements parsed
        self._seen = 0
        # total number of potential elements to request, some services don't
        # return the number of matching elements so this is optional
        # TODO: for services that return total number of matches, send async requests
        self._total = None

    def send(self):
        while True:
            data = self.service.send(self)
            seen = 0
            for x in data:
                seen += 1
                yield x

            # no more results exist, stop requesting them
            if self.service.max_results is None or seen < self.service.max_results:
                break

            # set offset and send new request
            self._seen += seen
            self.params[self._offset_key] = self._seen
            self._finalized = False


class RPCRequest(Request):
    """Construct an RPC request."""

    def __init__(self, command, **kw):
        super().__init__(method='POST', **kw)
        self.command = command

    def _finalize(self):
        """Encode the data body of the request."""
        super()._finalize()
        self._req.data = self.service._encode_request(self.command, self.params)


class RESTRequest(Request):
    """Construct a REST request."""

    def __init__(self, endpoint, method='GET', **kw):
        self.method = method
        self.endpoint = endpoint
        self.data = None
        super().__init__(method=method, **kw)

    @property
    def url(self):
        """Construct a full resource URL with params encoded."""
        l = []
        for k, v in self.params.items():
            if isinstance(v, (list, tuple)):
                l.extend((k, i) for i in v)
            else:
                l.append((k, v))

        params_str = f'?{urlencode(l)}' if l else ''
        return f"{self.service._base}/{self.endpoint.lstrip('/')}{params_str}"

    def _finalize(self):
        """Set the request URL using the specified params and encode the data body."""
        # inject auth params if available
        super()._finalize()

        # construct URL to resource with requested params
        self._req.url = self.url

        # encode additional params to data body
        if self.data:
            self._req.data = self.service._encode_request(self.data)


class NullRequest(Request):
    """Placeholder request that does nothing."""

    def __init__(self, generator=False):
        super().__init__(service=None)
        self._generator = generator
        self._reqs = (None,)

    def __bool__(self):
        return False

    def parse(self, data):
        if not self._generator:
            return None

        while True:
            yield None


class Service(object):
    """Generic service support."""

    _service = None
    _cache_cls = Cache
    _client_callbacks = []

    item = Item
    item_endpoint = None
    attachment = Attachment
    attachment_endpoint = None

    def __init__(self, base, endpoint='', connection=None, verify=True, user=None, password=None,
                 auth_file=None, auth_token=None, suffix=None, timeout=None, concurrent=None,
                 max_results=None, debug=None, verbose=None, **kw):
        self.base = base
        self.webbase = base
        self.user = user
        self.password = password
        self.suffix = suffix
        self.verify = verify
        self.verbose = verbose
        self.debug = debug
        self.timeout = timeout if timeout is not None else 30
        self.max_results = max_results

        # max workers defaults to system CPU count * 5 if concurrent is None
        self.executor = ThreadPoolExecutor(max_workers=concurrent)
        self.concurrent = self.executor._max_workers

        url = urlparse(self.base)
        self._base = urlunparse((
            url.scheme,
            url.netloc,
            url.path.rstrip('/') + endpoint,
            None, None, None))

        self.authenticated = False
        self.cache = self._cache_cls(connection)
        self.auth = Auth(connection, path=auth_file, token=auth_token)

        # block when urllib3 connection pool is full
        s = requests.Session()
        a = requests.adapters.HTTPAdapter(pool_maxsize=self.concurrent, pool_block=True)
        s.mount('https://', a)
        s.mount('http://', a)
        self.session = s
        self._web_session = None

        # Suppress insecure request warnings if SSL cert verification is
        # disabled. Since it's enabled by default we assume when it's disabled
        # the user knows what they're doing.
        if not self.verify:
            warnings.simplefilter('ignore', urllib3.exceptions.InsecureRequestWarning)

        self.session.headers['User-Agent'] = f'{__title__}-{__version__}'
        self.session.headers['Accept-Encoding'] = ', '.join(('gzip', 'deflate', 'compress'))

        # login if user/pass was specified and the auth token isn't set
        if not self.auth and user is not None and password is not None:
            self.login(user, password, **kw)

    @property
    def cache_updates(self):
        """Pull latest data from service for cache update."""
        return {}

    def login(self, user, password, **kw):
        """Authenticate a session."""
        if user is None or password is None:
            raise BiteError('both user and password parameters must be specified')

        token = self._get_auth_token(user, password, **kw)
        self.auth.update(token)

    def _get_auth_token(self, user=None, password=None, **kw):
        """Get an authentication token from the service."""
        return self.send(self.LoginRequest(user=user, password=password, **kw))

    def __str__(self):
        return f'{self.webbase} -- {self._service}'

    @staticmethod
    def _encode_request(method, params=None):
        """Encode the data body for a request."""
        raise NotImplementedError

    @staticmethod
    def _decode_request(request):
        """Decode the data body of a request."""
        raise NotImplementedError

    def inject_auth(self, request=None, params=None):
        """Inject authentication into a request or session."""
        return request, params

    def parse_response(self, response):
        """Parse the returned response."""
        raise NotImplementedError

    def web_session(self, login=True):
        """Start a session with the service's website.

        Useful for automating screen scraping when absolutely required.
        """
        if self._web_session is not None:
            return self._web_session

        if login:
            user, password = self.user, self.password
            while not all((user, password)):
                user, password = self.client.get_user_pass()
        else:
            user, password = None, None
        self._web_session = self.WebSession(self, user, password)
        return self._web_session

    class WebSession(object):
        """Context manager for a requests session targeting the service's website."""

        def __init__(self, service, user=None, password=None):
            self.service = service
            # TODO: cache/reload cookies across runs?
            self.session = requests.Session()
            self.params = {}
            self.authenticate = all((user, password))
            self.authenticated = False
            if self.authenticate:
                self.add_params(user, password)

        def add_params(self, user, password):
            """Add login params to send to the service."""
            raise NotImplementedError

        def login(self):
            """Login via the web UI for the service."""
            self.authenticated = True

        def __enter__(self):
            # pull site to set any required cookies
            if not self.session.cookies:
                self.session.get(self.service.webbase)
            if not self.authenticated and self.authenticate:
                self.login()
            return self.session

        def __exit__(self, *args):
            pass

        def __del__(self):
            # close during removal instead of __exit__ so we can reuse the
            # context handler
            self.session.close()

    def send(self, *reqs):
        """Send requests and return parsed response data."""
        if not reqs:
            return None

        def _raise(e): raise
        ident = lambda x: x

        def _parse(parse, handle, reqs):
            generator = getattr(parse, 'generator', False)
            try:
                if len(reqs) > 1 or generator:
                    results = (x.result() for x in reqs)
                else:
                    results = reqs[0].result()
                return parse(results)
            except RequestError as e:
                handle(e)

        def _send_jobs(reqs):
            jobs = []
            for req in iflatten_instance(reqs, Request):
                parse = getattr(req, 'parse', ident)
                handle = getattr(req, 'handle_exception', _raise)

                if isinstance(req, Request) and len(req) > 1:
                    # force subreqs to be sent and parsed in parallel
                    data = _send_jobs(iter(req))
                    jobs.append(self.executor.submit(_parse, parse, handle, data))
                else:
                    http_reqs = []
                    if not hasattr(req, '__iter__'):
                        req = [req]

                    for r in iflatten_instance(req, requests.Request):
                        if isinstance(r, requests.Request):
                            func = self._http_send
                        else:
                            func = ident
                        http_reqs.append(self.executor.submit(func, r))

                    if http_reqs:
                        jobs.append(self.executor.submit(_parse, parse, handle, http_reqs))
            return jobs

        data = (x.result() for x in _send_jobs(reqs))

        generator = isinstance(reqs[0], (list, tuple))
        if len(reqs) == 1 and not generator:
            return next(data)
        else:
            return data

    def _http_send(self, req):
        """Send an HTTP request and return the parsed response."""
        try:
            response = self.session.send(
                self.session.prepare_request(req), stream=True, timeout=self.timeout,
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
            raise RequestError(f'service moved permanently: {old} -> {new}')

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
                error_str = f'HTTP Error {response.status_code}'
                reason = response.reason.lower()
                if reason:
                    error_str += f': {reason}'
                elif not self.verbose:
                    error_str += ' (enable verbose mode to see server response)'
                raise RequestError(
                    error_str, text=response.text, code=response.status_code)

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
