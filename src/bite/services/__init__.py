import configparser
import os
import stat
import sys
from urllib.parse import urlparse, urlunparse

import concurrent.futures
import requests

from .. import __version__
from ..exceptions import RequestError, AuthError, NotFound
from ..config import update_config
from ..const import USER_CACHE_PATH


def command(name):
    """Register a service command."""
    def wrapped(cls, *args, **kwds):
        func = lambda self, *args, **kw: cls(self, *args, **kw)
        setattr(Service, name, func)
        return cls
    return wrapped

class Request(object):
    errors = {
        403: AuthError,
        404: NotFound,
    }

    def __init__(self, service):
        self.service = service
        self.requests = []

    def send(self):
        if len(self.requests) > 1:
            return self.parse(self.service.parallel_send(self.requests))
        else:
            return self.parse(self.service.send(self.requests[0]))

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

class NullRequest(Request):

    def send(self):
        pass


class Service(object):

    def __init__(self, base, connection=None, verify=True, user=None, password=None, skip_auth=True,
                 auth_token=None, suffix=None, timeout=None, auth_file=None, cache=None, **kw):
        self.connection = connection
        self.base = base
        self.user = user
        self.password = password
        self.suffix = suffix
        self.cache = cache if cache is not None else {}
        self.verify = verify
        self.timeout = timeout if timeout is not None else 30

        url = urlparse(self.base)
        self._base = urlunparse((
            url.scheme,
            url.netloc,
            url.path.rstrip('/') + kw.get('endpoint', ''),
            None, None, None))

        self.item = 'issue'
        self.item_web_endpoint = None

        file_name = self.connection
        if file_name is None:
            url = urlparse(self.service.base)
            if len(url.path) <= 1:
                file_name = url.netloc
            else:
                file_name = '{}{}'.format(url.netloc, url.path.rstrip('/').replace('/', '-'))
            if url.username is not None or url.password is not None:
                file_name = file_name.split('@', 1)[1]
        self.cached_config = os.path.join(USER_CACHE_PATH, 'config', file_name)
        self.load_cache()

        self.skip_auth = skip_auth
        self.auth_token = auth_token
        if auth_file is None:
            self.auth_file = os.path.join(USER_CACHE_PATH, 'auth', file_name)
        else:
            self.auth_file = auth_file

        self.session = requests.Session()
        self.session.headers['User-Agent'] = '{}-{}'.format('bite', __version__)
        self.session.headers['Accept-Encoding'] = ', '.join(('gzip', 'deflate', 'compress'))

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

    def _cache_update(self):
        """Pull latest data from service for cache update."""
        return None

    def cache_update(self):
        """Update cached data for the service."""
        data = self._cache_update()
        if data is not None:
            try:
                os.makedirs(os.path.dirname(self.cached_config))
            except FileExistsError:
                pass
            update_config(self.cached_config, self.connection, data)

    def load_cache(self):
        """Load cached data from config."""
        try:
            with open(self.cached_config, 'r') as f:
                config = configparser.ConfigParser()
                config.read(self.cached_config)
                settings = config.items(self.connection)
        except IOError:
            settings = ()
        # XXX: currently assumes all cached data is CSV
        self.cache.update(
            (k, tuple(x.strip() for x in v.split(',')))
            for k, v in config.items(self.connection))

    def encode_request(self, method, params=None):
        """Encode the data body for a request."""
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

    def send(self, req, raw=False):
        """Send raw request and return a response."""
        try:
            response = self.session.send(
                req, stream=True, timeout=self.timeout, verify=self.verify, allow_redirects=False)
        except requests.exceptions.SSLError as e:
            raise RequestError('SSL certificate verification failed')
        except requests.exceptions.ConnectionError as e:
            raise RequestError('failed to establish connection')
        except requests.exceptions.ReadTimeout as e:
            raise RequestError('request timed out')

        if response.status_code in (301,):
            old = self.base
            new = response.headers['Location']
            if new.endswith(self.endpoint):
                new = new[:-len(self.endpoint)]
            raise RequestError('service moved permanently: {} -> {}'.format(old, new))

        if response.ok:
            if raw:
                return response
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

    def parallel_send(self, reqs, size=8, block=True):
        """Run parallel requests at once."""
        jobs = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=size) as executor:
            for req in reqs:
                if isinstance(req, tuple) or isinstance(req, list):
                    yield self.parallel_send(req)
                else:
                    # XXX: hack to support both internal request format and HTTP requests
                    if isinstance(req, Request):
                        jobs.append(executor.submit(lambda x: x.send(), req))
                    else:
                        jobs.append(executor.submit(self.send, req))

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
