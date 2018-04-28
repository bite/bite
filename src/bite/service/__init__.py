from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse, urlunparse

import requests
from snakeoil.demandload import demandload
from snakeoil.sequences import iflatten_instance

from ._reqs import Request
from .. import __title__, __version__
from ..cache import Cache, Auth, Cookies
from ..exceptions import RequestError, AuthError, BiteError
from ..objects import Item, Attachment

demandload(
    'warnings',
    'urllib3',
)


class ClientCallbacks(object):
    """Client callback stubs used by services."""

    def get_user_pass(self):
        """Request user/password info from the user if not available."""
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
    _cache_cls = Cache

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

        self.client = ClientCallbacks()

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

        self.cookies = Cookies(connection)
        self.cookies.load()

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
        self._web_session = self.WebSession(self, login)
        return self._web_session

    class WebSession(object):
        """Context manager for a requests session targeting the service's website."""

        def __init__(self, service, login=True):
            self.service = service
            self.authenticate = login
            self.authenticated = False
            self.session = requests.Session()
            self.session.cookies = self.service.cookies
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
                self.try_login(str(e))

        def __enter__(self):
            # If we're not logged in and require it, perform a login sequence.
            msg = None
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
        if response.status_code == 401:
            raise AuthError('authentication failed', text=response.text)
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
