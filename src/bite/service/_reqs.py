from functools import wraps, partial
import re

import requests


def req_cmd(service_cls, name=None, cmd=None, obj_args=False):
    """Register service request and command functions."""
    def wrapped(req_name, cls, *args, **kwds):
        req_func = lambda self, *args, **kw: cls(*args, service=self, **kw)
        if req_name is None:
            req_name = re.match(r'^_?([a-zA-Z]+).*$', cls.__name__)
            if not req_name:
                raise ValueError(f'invalid request name: {cls.__name__!r}')
            req_name = req_name.group(1)
        setattr(service_cls, req_name, req_func)
        if cmd is not None:
            send = getattr(service_cls, 'send')
            # TODO: figure out a better funcion overloading method
            def send_func(self, *args, **kw):
                # support passing in item object iterables for marked reqs
                if obj_args and (args and not kw):
                    reqs = tuple(cls(service=self, **item) for item in args)
                    return send(self, Request(service=self, reqs=reqs))
                return send(self, cls(*args, service=self, **kw))
            setattr(service_cls, cmd, send_func)
        return cls
    return partial(wrapped, name)


def generator(func):
    """Register request creation function."""
    @wraps(func)
    def wrapped(*args, **kw):
        return func(*args, **kw)
    wrapped.generator = True
    return wrapped


class Request(object):
    """Construct a request."""

    def __init__(self, service, url=None, method=None, params=None, reqs=None, options=None, **kw):
        self.service = service
        self.options = options if options is not None else []
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
                reqs.append(self.service.session.prepare_request(r))
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

    # page, query size, and total results parameter keys for a related service query
    _page_key = None
    _size_key = None
    _total_key = None

    def __init__(self, service, limit=None, page=None, *args, **kw):
        super().__init__(*args, service=service, **kw)

        if not all((self._page_key, self._size_key, self._total_key)):
            raise ValueError('page, size, and total keys must be set')

        # set a search limit to make continued requests work as expected
        if limit is not None:
            self.params[self._size_key] = limit
        elif service.max_results is not None:
            self.params[self._size_key] = service.max_results

        if page is not None:
            self.params[self._page_key] = page
        else:
            self.params[self._page_key] = 0

        # total number of elements parsed
        self._seen = 0

        # Total number of potential elements to request, some services don't
        # return the number of matching elements so this is optional.
        # TODO: For services that return total number of matches on the first
        # request, send the remaining requests asynchronously.
        self._total = None

    def send(self):
        while True:
            data = self.service.send(self)
            seen = 0
            for x in data:
                seen += 1
                yield x

            # if no more results exist, stop requesting them
            self._seen += seen
            if self._total is None or self._seen >= self._total:
                break

            # increment page and send new request
            self.params[self._page_key] += 1
            self._finalized = False

    def parse(self, data):
        """Extract the total number of results expected."""
        if self._total is None:
            # Some services variably insert the total results number in
            # response objects based on how expensive it is to compute so allow
            # it to be missing.
            self._total = data.get(self._total_key, None)
        return super().parse(data)


# TODO: run these asynchronously
class FlaggedPagedRequest(Request):
    """Keep requesting matching records until all relevant results are returned."""

    # page, query size, and total results parameter keys for a related service query
    _page_key = None
    _size_key = None

    def __init__(self, service, limit=None, page=None, *args, **kw):
        super().__init__(*args, service=service, **kw)

        if not all((self._page_key, self._size_key)):
            raise ValueError('page and size keys must be set')

        # set a search limit to make continued requests work as expected
        if limit is not None:
            self.params[self._size_key] = limit
        elif service.max_results is not None:
            self.params[self._size_key] = service.max_results

        if page is not None:
            self.params[self._page_key] = page
        else:
            self.params[self._page_key] = 0

        # total number of elements parsed
        self._seen = 0

        # flag to note when all data has been consumed
        self._consumed = False

    def send(self):
        while True:
            data = self.service.send(self)
            seen = 0
            for x in data:
                seen += 1
                yield x

            # if no more results exist, stop requesting them
            if self._consumed:
                break

            # increment page and send new request
            self._seen += seen
            self.params[self._page_key] += 1
            self._finalized = False


# TODO: run these asynchronously
class OffsetPagedRequest(Request):
    """Keep requesting matching records until all relevant results are returned."""

    # offset and query size parameter keys for a related service query
    _offset_key = None
    _size_key = None

    # total results size key
    _total_key = None

    def __init__(self, service, limit=None, offset=None, *args, **kw):
        super().__init__(*args, service=service, **kw)

        if not all((self._offset_key, self._size_key)):
            raise ValueError('offset and size keys must be set')

        # set a search limit to make continued requests work as expected
        if limit is not None:
            self.params[self._size_key] = limit
        elif service.max_results is not None:
            self.params[self._size_key] = service.max_results

        if offset is not None:
            self.params[self._offset_key] = offset

        # total number of elements parsed
        self._seen = 0

        # Total number of potential elements to request, some services don't
        # return the number of matching elements so this is optional.
        # TODO: For services that return total number of matches on the first
        # request, send the remaining requests asynchronously.
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

    def parse(self, data):
        """Parse the data returned from a given request."""
        if self._total is None and self._total_key is not None:
            # Some services variably insert the total results number in
            # response objects based on how expensive it is to compute so allow
            # it to be missing.
            self._total = data.get(self._total_key, None)
        return super().parse(data)


# TODO: run these asynchronously
class LinkPagedRequest(Request):
    """Keep requesting matching records until all relevant result pages are returned."""

    # paging related parameter keys for a related service query
    _page = None
    _pagelen = None
    _next = None
    _previous = None

    # total results size key
    _total_key = None

    def __init__(self, service, *args, **kw):
        super().__init__(*args, service=service, **kw)

        if not all((self._page, self._pagelen, self._next, self._previous)):
            raise ValueError('page, pagelen, next, and previous keys must be set')

        if service.max_results is not None:
            self.params[self._pagelen] = service.max_results

        # total number of elements parsed
        self._seen = 0
        # link to next page
        self._next_page = None

        # Total number of potential elements to request, some services don't
        # return the number of matching elements so this is optional.
        # TODO: For services that return total number of matches on the first
        # request, send the remaining requests asynchronously.
        self._total = None

    def send(self):
        while True:
            data = self.service.send(self)
            seen = 0
            for x in data:
                seen += 1
                yield x

            # no more results exist, stop requesting them
            if self._next_page is None:
                break

            # set offset and send new request
            self._seen += seen
            self._req.url = self._next_page

    def parse(self, data):
        """Parse the data returned from a given request."""
        self._next_page = data.get(self._next, None)
        if self._total is None and self._total_key is not None:
            # Some services variably insert the total results number in
            # response objects based on how expensive it is to compute so allow
            # it to be missing.
            self._total = data.get(self._total_key, None)
        return super().parse(data)


class ParseRequest(Request):
    """Parse parameters according to defined methods for a request."""

    # map from args dest name to expected service parameter name
    _params_map = {}

    def __init__(self, service, method=None, **kw):
        super().__init__(service=service, method=method, **kw)
        self.param_parser = self.ParamParser(self)
        self.params = self.parse_params(**kw)

    def parse_params(self, **kw):
        for k, v in ((k, v) for (k, v) in kw.items() if v):
            parse = getattr(self.param_parser, k, self.param_parser._default_parser)
            if not callable(parse):
                raise ValueError(f"invalid parameter parsing function: {k!r}")
            parse(k, v)

        self.params = self.remap_params(self.params)
        params = self.param_parser._finalize()
        return params if params is not None else self.params

    def remap_params(self, dct, remap=None):
        """Remap dict keys to expected service parameter names."""
        if remap is None:
            remap = self._params_map
        for k in (remap.keys() & dct.keys()):
            kp = remap[k]
            dct[kp] = dct.pop(k)
        return dct

    class ParamParser(object):

        def __init__(self, request):
            self.request = request
            self.remap = request._params_map
            self.service = request.service
            self.params = request.params
            self.options = request.options

        def _finalize(self):
            """Finalize request parameters."""

        def _default_parser(self, k, v):
            """Default parameter parser."""


class NullRequest(Request):
    """Placeholder request that does nothing."""

    def __init__(self, generator=False):
        super().__init__(service=None)
        self._generator = generator
        self._reqs = (None,)
        self._finalized = True

    def _finalize(self):
        pass

    def __bool__(self):
        return False

    def __str__(self):
        return repr(self)

    def parse(self, data):
        if not self._generator:
            return None

        while True:
            yield None


class GetRequest(Request):
    """Construct requests to retrieve all known data for given item IDs."""

    def __init__(self, ids, service, get_comments=False, get_attachments=False,
                 get_changes=False, *args, **kw):
        if not ids:
            raise ValueError('No {service.item.type} ID(s) specified')

        reqs = [service.GetItemRequest(ids=ids)]
        for call in ('comments', 'attachments', 'changes'):
            if locals()[f'get_{call}']:
                reqs.append(getattr(service, f'{call.capitalize()}Request')(ids=ids))
            else:
                reqs.append(NullRequest(generator=True))

        super().__init__(service=service, reqs=reqs)

    def parse(self, data):
        items, comments, attachments, changes = data
        for item in items:
            item.comments = next(comments)
            item.attachments = next(attachments)
            item.changes = next(changes)
            yield item
