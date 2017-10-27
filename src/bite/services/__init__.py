import os
import stat
import sys
from urllib.parse import urlparse, urlunparse

import concurrent.futures
import requests

from .. import __version__
from ..exceptions import RequestError, AuthError, NotFound


def command(function):
    def wrapper(self, *args, **kw):
        request = getattr(self, function.__name__ + '_request')(*args, **kw)
        data = self.send(request)
        parse_fcn = getattr(self, function.__name__ + '_parse')
        return parse_fcn(data, *args, **kw)
    return wrapper

class Request(object):
    errors = {
        403: AuthError,
        404: NotFound,
    }

    def __init__(self, service):
        self.service = service

    def send(self):
        return self.parse(self.service.send(self.request))

    def __str__(self):
        return '{}\n{}\n\n{}'.format(
            self.request.method + ' ' + self.request.url,
            '\n'.join('{}: {}'.format(k, v) for k, v in self.request.headers.items()),
            self.request.body,
        )

    def parse(self, data):
        return data

class NullRequest(Request):
    def __init__(self):
        pass

    def send(self):
        pass


class Service(object):

    def __init__(self, base, verify=True, user=None, password=None, skip_auth=True,
                 auth_token=None, suffix=None, timeout=None, **kw):
        self.base = base
        self.user = user
        self.password = password
        self.suffix = suffix
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

        self.skip_auth = skip_auth
        self.auth_token = auth_token

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

    def __str__(self):
        return str(self.base)

    def cache_updates(self):
        """Update cached data for the service."""
        pass

    def encode_request(self, method, params):
        """Encode the data body for a request."""
        raise NotImplementedError()

    def inject_auth(self, params):
        """Add authentication data to a request."""
        raise NotImplementedError()

    def create_request(self, url=None, method=None, params=None):
        """Construct a request."""
        if url is None:
            url = self._base
        if params is None:
            params = {}

        if not self.skip_auth and self.auth_token is not None:
            params = self.inject_auth(params)

        data = self.encode_request(method, params)
        return self.session.prepare_request(
            requests.Request(method='POST', url=url, data=data))

    def parse_response(self, response):
        """Parse the returned response."""
        raise NotImplementedError()

    def send(self, req):
        """Send raw request and return raw response."""
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
                    jobs.append(executor.submit(lambda x: x.send(), req))

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
