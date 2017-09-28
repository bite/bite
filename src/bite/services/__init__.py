import logging
import os
import stat
import sys
from urllib.parse import urlparse

import concurrent.futures
import requests

from bite import __version__
from bite.exceptions import RequestError, AuthError, NotFound

#requests_log = logging.getLogger('requests')
#requests_log.setLevel(logging.DEBUG)
#from functools import wraps

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

    #def __unicode__(self):
    #    return '\n'.join(self.options)

    #def __str__(self):
    #    return unicode(self).encode('utf-8')

    #def __call__(*args, **kw):
    #    #return request(*args, **kw)
    #    raise NotImplementedError

    #def __get__():
    #    raise NotImplementedError

    def send(self):
        return self.parse(self.service.send(self.request))

        #try:
        #    return self.parse(self.service.send(self.request))
        #except Exception as e:
        #    error_code = str(e.response.status_code)
        #    if error_code in self.errors.keys():
        #        raise(self.errors[error_code](e))
        #    else:
        #        raise(e)

    def parse(self, data):
        return data

class NullRequest(Request):
    def __init__(self):
        pass

    def send(self):
        pass

class Service(object):
    def __init__(self, base, verify=True, user=None, password=None,
                 cookies=None, suffix=None, timeout=None, **kw):
        self.base = base
        self.user = user
        self.password = password
        self.suffix = suffix
        self.auth_token = cookies
        self.verify = verify
        self.timeout = timeout

        self.headers['User-Agent'] = '{}-{}'.format('bite', __version__)
        self.headers['Accept-Encoding'] = ', '.join(('gzip', 'deflate', 'compress'))
        if 'Accept' not in self.headers:
            self.headers['Accept'] = '*/*'

        self.session = requests.Session()

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

    def create_request(self, *args, **kw):
        """Construct a request object."""
        raise NotImplementedError

    def send(self, req):
        """Sends raw request and returns raw response."""
        #logging.debug(req.url)
        #logging.debug(req.headers)

        try:
            response = self.session.send(req, stream=True, timeout=self.timeout, verify=self.verify)
        except requests.exceptions.SSLError as e:
            raise RequestError('SSL certificate verification failed')
        except requests.exceptions.ConnectionError as e:
            raise RequestError('failed to establish connection')

        if response.ok:
            return response
        else:
            if response.status_code in (401, 403):
                raise AuthError('Authentication failed')
            else:
                try:
                    raise response.raise_for_status()
                except requests.exceptions.HTTPError:
                    raise RequestError('HTTP Error {}: {}'.format(
                        response.status_code, response.reason.lower()), text=response.text)

    #def _parallel_send(self, reqs, size=8, block=True):
    #    """Run parallel requests at once."""
    #    # TODO: tune this and merge all send functionality into cleaner api
    #    # http://www.dalkescientific.com/writings/diary/archive/2012/01/19/concurrent.futures.html
    #    with concurrent.futures.ThreadPoolExecutor(max_workers=size) as executor:
    #        jobs = [executor.submit(lambda x: x.send(), req) for req in reqs]
    #        for job in jobs:
    #            yield job.result()

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

                #if job.exception() is not None:
                #    print(dir(job.exception()))
                #else:
                #    yield job.result()
                #try:
                #    yield job.result()
                #except AttributeError:
                #    # TODO: fix this workaround for empty set cases
                #    yield None

            ## return as threads complete
            #for future in concurrent.futures.as_completed(jobs):
            #    yield future.result()

            #for resp in executor.map(self.send2, reqs):
            #    yield resp

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
