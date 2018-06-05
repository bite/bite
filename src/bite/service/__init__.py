from concurrent.futures import ThreadPoolExecutor
from functools import partial
from multiprocessing import cpu_count
from urllib.parse import urlparse, urlunparse

import requests
from snakeoil.demandload import demandload
from snakeoil.sequences import iflatten_instance

from ._reqs import Request, ExtractData
from .. import __title__, __version__
from ..cache import Cache, Auth, Cookies
from ..exceptions import RequestError, AuthError, BiteError
from ..objects import Item, Attachment

demandload(
    'warnings',
    'urllib3',
)


class Session(requests.Session):

    def __init__(self, concurrent=None, verify=True, stream=True,
                 timeout=None, allow_redirects=False):
        super().__init__()
        self.verify = verify
        self.stream = stream
        self.allow_redirects = allow_redirects
        if timeout == 0:
            # set timeout to 0 to never timeout
            self.timeout = None
        else:
            # default to timing out connections after 30 seconds
            self.timeout = timeout if timeout is not None else 30

        # block when urllib3 connection pool is full
        concurrent = concurrent if concurrent is not None else cpu_count() * 5
        a = requests.adapters.HTTPAdapter(pool_maxsize=concurrent, pool_block=True)
        self.mount('https://', a)
        self.mount('http://', a)

        # Suppress insecure request warnings if SSL cert verification is
        # disabled. Since it's enabled by default we assume when it's disabled
        # the user knows what they're doing.
        if not self.verify:
            warnings.simplefilter('ignore', urllib3.exceptions.InsecureRequestWarning)

        self.headers['User-Agent'] = f'{__title__}-{__version__}'
        self.headers['Accept-Encoding'] = ', '.join(('gzip', 'deflate', 'compress'))

    def send(self, req, **kw):
        # use session settings if not explicitly passed
        kw.setdefault('timeout', self.timeout)
        kw.setdefault('allow_redirects', self.allow_redirects)

        if not isinstance(req, requests.PreparedRequest):
            req = self.prepare_request(req)

        try:
            return super().send(req, **kw)
        except requests.exceptions.RequestException as e:
            if isinstance(e, requests.exceptions.SSLError):
                msg = 'SSL certificate verification failed'
            elif isinstance(e, requests.exceptions.ConnectionError):
                url = urlparse(req.url)
                base_url = urlunparse((
                    url.scheme,
                    url.netloc,
                    '',
                    None, None, None))
                msg = f'failed to establish connection: {base_url}'
            elif isinstance(e, requests.exceptions.ReadTimeout):
                msg = f'request timed out (timeout: {self.timeout}s)'
            else:
                msg = str(e)
            raise RequestError(msg, request=e.request, response=e.response)


class ClientCallbacks(object):
    """Client callback stubs used by services."""

    def get_user_pass(self):
        """Request user/password info from the user if not available."""
        raise NotImplementedError

    def login(self, s):
        """Interactively login to a service."""
        raise NotImplementedError

    def confirm(self, *args, **kw):
        """Prompts for yes or no response from the user."""
        raise NotImplementedError

    def progress_output(self, s):
        """Output a progress message."""
        raise NotImplementedError


class Service(object):
    """Generic service support."""

    _service = None
    _service_error_cls = RequestError
    _cache_cls = Cache

    item = Item
    item_endpoint = None
    attachment = Attachment
    attachment_endpoint = None

    def __init__(self, *, base, endpoint='', connection=None, verify=True, user=None, password=None,
                 auth_file=None, auth_token=None, suffix=None, timeout=None, concurrent=None,
                 max_results=None, debug=None, verbose=None, **kw):
        self.base = base
        self.webbase = base
        self.connection = connection
        self.user = user
        self.password = password
        self.suffix = suffix
        self.verbose = verbose
        self.debug = debug
        self.max_results = max_results

        self.client = ClientCallbacks()

        # max workers defaults to system CPU count * 5 if concurrent is None
        self.executor = ThreadPoolExecutor(max_workers=concurrent)

        url = urlparse(self.base)
        self._base = urlunparse((
            url.scheme,
            url.netloc,
            url.path.rstrip('/') + endpoint,
            None, None, None))

        self.authenticated = False
        self.cache = self._cache_cls(connection=connection)
        self.auth = Auth(connection, path=auth_file, token=auth_token)

        concurrent = self.executor._max_workers
        self.session = Session(concurrent=concurrent, verify=verify, timeout=timeout)
        self._web_session = None

        # login if user/pass was specified and the auth token isn't set
        if not self.auth and all((user, password)):
            self.login(user=user, password=password, **kw)

    @property
    def cache_updates(self):
        """Pull latest data from service for cache update."""
        return {}

    def login(self, *, user, password, **kw):
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

    def item_urls(self, ids):
        """Generate item URLs for specified item IDs."""
        if self.item_endpoint is None:
            raise BiteError(f"no web endpoint defined for {self.item.type}s")

        if self.item_endpoint.startswith('/'):
            url = self.webbase.rstrip('/') + self.item_endpoint
        else:
            url = self.item_endpoint

        yield from self._format_item_urls(url, ids)

    def _format_item_urls(self, url, ids):
        """Format item URLs from given information."""
        for i in ids:
            yield url.format(id=i)

    def attachment_urls(self, ids):
        """Generate attachment URLs for specified attachment IDs."""
        if self.attachment_endpoint is None:
            raise BiteError("no web endpoint defined for attachments")

        if self.attachment_endpoint.startswith('/'):
            url = self.webbase.rstrip('/') + self.attachment_endpoint
        else:
            url = self.attachment_endpoint

        yield from self._format_attachment_urls(url, ids)

    def _format_attachment_urls(self, url, ids):
        """Format attachment URLs from given information."""
        for i in ids:
            yield url.format(id=i)

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

    def handle_error(self, *, code, msg):
        """Handle service specific errors."""
        raise self._service_error_cls(msg=msg, code=code)

    def web_session(self, login=True):
        """Start a session with the service's website.

        Useful for automating screen scraping when absolutely required.
        """
        if self._web_session is not None:
            return self._web_session
        self._web_session = self.WebSession(self, login)
        return self._web_session

    class WebSession(object):
        """Context manager for a requests session targeting the service's website."""

        def __init__(self, service, login=True):
            self.service = service
            self.authenticate = login
            self.authenticated = False
            self.session = Session()
            self.session.cookies = Cookies(self.service.connection)
            self.session.cookies.load()
            self.params = {}

        def add_params(self, user, password):
            """Add login params to send to the service."""
            raise NotImplementedError

        def interactive_login(self, msg=None):
            """Force an interactive login using user/password info."""
            user, password = self.service.user, self.service.password
            while not all((user, password)):
                user, password = self.service.client.get_user_pass(msg)
            self.add_params(user, password)

        def logged_in(self, r):
            """Check if we're logged in to the service."""
            raise NotImplementedError

        def login(self):
            """Login via the web UI for the service."""
            self.authenticated = True

        def try_login(self, msg=None):
            """Repeatedly try to login until successful."""
            orig_cookies = list(self.session.cookies)
            # Pull site to set any required cookies and check login status if
            # cookies were set.
            r = self.session.get(self.service.webbase)
            if self.logged_in(r):
                return True
            # cookies are bad, force login and refresh them
            if orig_cookies:
                self.session.cookies.clear()
                for x in r.cookies:
                    self.session.cookies.set_cookie(x)
            self.interactive_login(msg)
            try:
                self.login()
            except AuthError as e:
                self.try_login(msg=str(e))

        def __enter__(self):
            # If we're not logged in and require it, perform a login sequence.
            if self.authenticate:
                while not self.authenticated:
                    self.try_login()
            return self.session

        def __exit__(self, *args):
            pass

        def __del__(self):
            # close during removal instead of __exit__ so we can reuse the
            # context handler
            if self.authenticated:
                self.session.cookies.save()
            self.session.close()

    def send(self, *reqs, **kw):
        """Send requests and return parsed response data."""
        # TODO: simplify this using async/await
        if not reqs:
            return None

        ident = lambda x: x

        def _parse(parse, iterate, reqs, generator=False):
            results = iterate(x.result() for x in reqs)
            if len(reqs) == 1 and not generator:
                results = next(results)
            return parse(results)

        def _send_jobs(reqs):
            jobs = []
            for req in iflatten_instance(reqs, Request):
                parse = getattr(req, 'parse', ident)
                iterate = getattr(req, '_iterate', ExtractData)
                req_parse = getattr(req, 'parse_response', None)
                raw = getattr(req, '_raw', None)
                generator = bool(getattr(req, '_reqs', ()))

                if isinstance(req, Request) and len(req) > 1:
                    # force subreqs to be sent and parsed in parallel
                    data = _send_jobs(iter(req))
                    jobs.append(self.executor.submit(_parse, parse, iterate, data))
                else:
                    http_reqs = []
                    if not hasattr(req, '__iter__'):
                        req = [req]

                    for r in iflatten_instance(req, requests.Request):
                        if isinstance(r, requests.Request):
                            func = partial(
                                self._http_send, raw=raw, req_parse=req_parse, **kw)
                        else:
                            func = ident
                        http_reqs.append(self.executor.submit(func, r))

                    if http_reqs:
                        jobs.append(self.executor.submit(
                            _parse, parse, iterate, http_reqs, generator))
            return jobs

        data = (x.result() for x in _send_jobs(reqs))

        generator = isinstance(reqs[0], (list, tuple))
        if len(reqs) == 1 and not generator:
            return next(data)
        else:
            return data

    def _http_send(self, req, raw=None, req_parse=None, **kw):
        """Send an HTTP request and return the parsed response."""
        response = self.session.send(req, **kw)

        if response.status_code == 301:
            old = self.base
            new = response.headers['Location']
            raise RequestError(
                f'service moved permanently: {old} -> {new}',
                request=req, response=response)

        if response.ok:
            # allow the request to parse itself as requested
            if req_parse is not None:
                return req_parse(response)
            # return the raw content of the response either in bytes or unicode
            elif raw:
                raw = 'content' if raw is True else raw
                return getattr(response, raw)
            return self.parse_response(response)
        else:
            self._failed_http_response(response)

    def _failed_http_response(self, response):
        if response.status_code == 401:
            raise AuthError('authentication failed', text=response.text)
        else:
            try:
                raise response.raise_for_status()
            except requests.exceptions.HTTPError as e:
                error_str = f'HTTP Error {response.status_code}'
                reason = e.response.reason.lower()
                if reason:
                    error_str += f': {reason}'
                elif not self.verbose:
                    error_str += ' (enable verbose mode to see server response)'
                raise RequestError(
                    error_str, text=e.response.text, code=e.response.status_code,
                    request=e.request, response=e.response)

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
