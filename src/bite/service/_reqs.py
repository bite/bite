from functools import wraps, partial
import re

import requests
from snakeoil.strings import pluralism


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
            # TODO: figure out a better function overloading method
            def send_func(self, *args, **kw):
                # support passing in item object iterables for marked reqs
                if obj_args and (args and not kw):
                    reqs = tuple(cls(service=self, **item) for item in args)
                    return send(self, Request(service=self, reqs=reqs))
                return send(self, cls(*args, service=self, **kw))
            setattr(service_cls, cmd, send_func)
        return cls
    return partial(wrapped, name)


class Request(object):
    """Construct a request."""

    def __init__(self, *, service, url=None, method=None, params=None,
                 reqs=None, options=None, raw=False, **kw):
        self.service = service
        self.options = options if options is not None else []
        self.params = params if params is not None else {}
        self._raw = raw
        self._finalized = False

        if method is not None:
            url = url if url is not None else self.service._base
            self._req = requests.Request(method=method, url=url)
        else:
            self._req = None

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

    def send(self, **kw):
        """Send a request object to the related service."""
        return self.service.send(self, **kw)

    def handle_exception(self, e):
        raise e

    def __len__(self):
        return len(list(self._requests))

    def __iter__(self):
        return self._requests

    @property
    def _none_gen(self):
        while True:
            yield None


class _BasePagedRequest(Request):

    # total results parameter key for a related service query
    _total_key = None

    def __init__(self, **kw):
        super().__init__(**kw)

        # total number of elements parsed
        self._seen = 0

        # Total number of potential elements to request, some services don't
        # return the number of matching elements so this is optional.
        # TODO: For services that return total number of matches on the first
        # request, send the remaining requests asynchronously.
        self._total = None

    def parse(self, data):
        """Extract the total number of results expected."""
        if self._total is None:
            # Some services variably insert the total results number in
            # response objects based on how expensive it is to compute so allow
            # it to be missing.
            if self._total_key is not None:
                self._total = data.get(self._total_key)
        return super().parse(data)

    def send(self):
        """Send a request object to the related service."""
        while True:
            data = self.service.send(self)
            for x in data:
                self._seen += 1
                yield x
            self.next_page()

    def next_page(self):
        """Modify a request in order to grab the next page of results."""
        raise StopIteration


# TODO: run these asynchronously
class PagedRequest(_BasePagedRequest):
    """Keep requesting matching records until all relevant results are returned."""

    # page and query size parameter keys for a related service query
    _page_key = None
    _size_key = None

    def __init__(self, limit=None, page=None, **kw):
        super().__init__(**kw)

        if not all((self._page_key, self._size_key, self._total_key)):
            raise ValueError('page, size, and total keys must be set')

        # set a search limit to make continued requests work as expected
        if limit is not None:
            self.params[self._size_key] = limit
            self.options.append(f'Limit: {limit}')
        elif self.service.max_results is not None:
            self.params[self._size_key] = self.service.max_results

        if page is not None:
            self.params[self._page_key] = page
            self.options.append(f'Page: {page}')
        else:
            self.params[self._page_key] = 0

    def next_page(self):
        # if no more results exist, stop requesting them
        if self._total is None or self._seen >= self._total:
            raise StopIteration

        # increment page param
        self.params[self._page_key] += 1
        self._finalized = False


# TODO: run these asynchronously
class FlaggedPagedRequest(_BasePagedRequest):
    """Keep requesting matching records until all relevant results are returned."""

    # page, query size, and total results parameter keys for a related service query
    _page_key = None
    _size_key = None

    def __init__(self, limit=None, page=None, **kw):
        super().__init__(**kw)

        if not all((self._page_key, self._size_key)):
            raise ValueError('page and size keys must be set')

        # set a search limit to make continued requests work as expected
        if limit is not None:
            self.params[self._size_key] = limit
            self.options.append(f'Limit: {limit}')
        elif self.service.max_results is not None:
            self.params[self._size_key] = self.service.max_results

        if page is not None:
            self.params[self._page_key] = page
            self.options.append(f'Page: {page}')
        else:
            self.params[self._page_key] = 0

        # flag to note when all data has been consumed
        self._exhausted = False

    def next_page(self):
        if self._exhausted:
            raise StopIteration

        # increment page param
        self.params[self._page_key] += 1
        self._finalized = False


# TODO: run these asynchronously
class OffsetPagedRequest(_BasePagedRequest):
    """Keep requesting matching records until all relevant results are returned."""

    # offset and query size parameter keys for a related service query
    _offset_key = None
    _size_key = None

    def __init__(self, limit=None, offset=None, **kw):
        super().__init__(**kw)

        if not all((self._offset_key, self._size_key)):
            raise ValueError('offset and size keys must be set')

        # set a search limit to make continued requests work as expected
        if limit is not None:
            self.params[self._size_key] = limit
            self.options.append(f'Limit: {limit}')
        elif self.service.max_results is not None:
            self.params[self._size_key] = self.service.max_results

        if offset is not None:
            self.params[self._offset_key] = offset

        # total number of elements parsed at previous paged request
        self._prev_seen = 0

    def next_page(self):
        seen = self._seen - self._prev_seen

        # no more results exist, stop requesting them
        if self.service.max_results is None or seen < self.service.max_results:
            raise StopIteration

        # set offset and send new request
        self._prev_seen = self._seen
        self.params[self._offset_key] = self._seen
        self._finalized = False


# TODO: run these asynchronously
class LinkPagedRequest(_BasePagedRequest):
    """Keep requesting matching records until all relevant result pages are returned."""

    # paging related parameter keys for a related service query
    _page = None
    _pagelen = None
    _next = None
    _previous = None

    def __init__(self, **kw):
        super().__init__(**kw)

        if not all((self._page, self._pagelen, self._next, self._previous)):
            raise ValueError('page, pagelen, next, and previous keys must be set')

        if self.service.max_results is not None:
            self.params[self._pagelen] = self.service.max_results

        # link to next page
        self._next_page = None

    def next_page(self):
        # no more results exist, stop requesting them
        if self._next_page is None:
            raise StopIteration

        # set offset and send new request
        self._req.url = self._next_page

    def parse(self, data):
        """Parse the data returned from a given request."""
        self._next_page = data.get(self._next)
        return super().parse(data)


# TODO: run these asynchronously
class LinkHeaderPagedRequest(_BasePagedRequest):
    """Keep requesting matching records until all relevant result pages are returned."""

    # total results response header key
    _pagelen = None
    _total_header = None

    def __init__(self, **kw):
        super().__init__(**kw)

        if all((self.service.max_results, self._pagelen)):
            self.params[self._pagelen] = self.service.max_results

        # link to next page
        self._next_page = None

    def parse_response(self, response):
        if self._total_header is not None:
            self._total = response.headers.get(self._total_header)
        self._next_page = response.links.get('next', {}).get('url')

    def next_page(self):
        # no more results exist, stop requesting them
        if self._next_page is None:
            raise StopIteration

        # set offset and send new request
        self._req.url = self._next_page


class ParseRequest(Request):
    """Parse parameters according to defined methods for a request."""

    # map from args dest name to expected service parameter name
    _params_map = {}

    def __init__(self, params=None, **kw):
        self.service = kw['service']
        self.options = kw.get('options', [])
        self.params = {}
        self.strict = True

        # accept unsplit kwargs as well
        if params is None:
            params = kw
            self.strict = False

        # parse given arguments using defined methods
        self.param_parser = self.ParamParser(request=self)
        self.unused_params = params.copy()
        self.parse_params(**params)

        # passed unparsed params to parent class
        kw.update(self.unused_params)
        kw['params'] = self.params
        kw['options'] = self.options
        super().__init__(**kw)

    def parse_params(self, **kw):
        for k, v in kw.items():
            parse = getattr(self.param_parser, k, None)
            if parse is None:
                parse = self.param_parser._default_parser
                if parse(k, v) is not None:
                    del self.unused_params[k]
            else:
                if not callable(parse):
                    if self.strict:
                        raise ValueError(f"invalid parameter parsing function: {k!r}")
                    continue
                parse(k, self.unused_params.pop(k))

        self.params = self.remap_params(self.params)
        params = self.param_parser._finalize()
        if params is not None:
            self.params = params

    def remap_params(self, dct, remap=None):
        """Remap dict keys to expected service parameter names."""
        if remap is None:
            remap = self._params_map
        for k in (remap.keys() & dct.keys()):
            kp = remap[k]
            dct[kp] = dct.pop(k)
        return dct

    class ParamParser(object):

        def __init__(self, *, request):
            self.request = request
            self.remap = request._params_map
            self.service = request.service
            self.params = request.params
            self.options = request.options

        def _finalize(self):
            """Finalize request parameters."""

        def _default_parser(self, k, v):
            """Default parameter parser."""


class Filter(object):
    """Stub for data filter."""

    def __init__(self, *, request, service, **kw):
        self.request = request
        self.options = request.options
        self.service = service

    def send(self, **kw):
        """Send a request object to the related service."""
        return self.request.send(**kw)


class CommentsFilter(Filter):

    def __init__(self, creator=None, attachment=None, comment_num=None, **kw):
        super().__init__(**kw)
        self.creator = set(creator) if creator else creator
        self.attachment = attachment
        self.comment_num = set(comment_num) if comment_num else comment_num

        if self.creator is not None:
            self.options.append(f"Creator{pluralism(self.creator)}: {', '.join(self.creator)}")
        if self.attachment:
            self.options.append('Attachments: yes')
        if self.comment_num is not None:
            self.options.append(
                f"Comment number{pluralism(self.comment_num)}: {', '.join(map(str, self.comment_num))}")

    def send(self, **kw):
        """Filter the returned data."""
        data = super().send(**kw)

        for i, comments in zip(self.request.ids, data):
            if self.creator is not None:
                comments = (x for x in comments if x.creator in self.creator)
            if self.attachment:
                comments = (x for x in comments if x.changes['attachment_id'] is not None)
            if self.comment_num is not None:
                if any(x < 0 for x in self.comment_num):
                    comments = list(comments)
                    selected = []
                    for x in comment_num:
                        try:
                            selected.append(comments[x])
                        except IndexError:
                            pass
                    comments = selected
                else:
                    comments = (x for x in comments if x.count in self.comment_num)
            yield i, comments


class ChangesFilter(Filter):

    def __init__(self, creator=None, attachment=None,
                 change_num=None, match=None, created=None, **kw):
        super().__init__(**kw)
        self.creator = set(map(self.service._resuffix, creator)) if creator else creator
        self.change_num = set(change_num) if change_num else change_num
        self.match = match
        self.created = created

        if self.creator is not None:
            self.options.append(f"Creator{pluralism(self.creator)}: {', '.join(self.creator)}")
        if self.change_num is not None:
            self.options.append(
                f"Change number{pluralism(self.change_num)}: {', '.join(map(str, self.change_num))}")
        if self.match is not None:
            self.options.append(f"Matching: {', '.join(self.match)}")
        if self.created is not None:
            self.options.append(f'Created: {self.created} (since {self.created!r} UTC)')

    def send(self, **kw):
        """Filter the returned data."""
        data = super().send(**kw)

        for i, changes in zip(self.request.ids, data):
            if self.creator is not None:
                changes = (x for x in changes if x.creator in self.creator)
            if self.created is not None:
                changes = (x for x in changes if x.created >= self.created)
            if self.match is not None:
                changes = (event for event in changes if event.match(fields=self.match))
            if self.change_num is not None:
                if any(x < 0 for x in self.change_num):
                    changes = list(changes)
                    selected = []
                    for x in comment_num:
                        try:
                            selected.append(changes[x])
                        except IndexError:
                            pass
                    changes = selected
                else:
                    changes = (x for x in changes if x.count in self.change_num)
            yield i, changes


class NullRequest(Request):
    """Placeholder request that does nothing."""

    def __init__(self):
        super().__init__(service=None)
        self._reqs = (None,)
        self._finalized = True

    def _finalize(self):
        pass

    def __bool__(self):
        return False

    def __str__(self):
        return repr(self)

    def parse(self, data):
        return self._none_gen


class GetRequest(Request):
    """Construct requests to retrieve all known data for given item IDs."""

    def __init__(self, ids, get_comments=True, get_attachments=True,
                 get_changes=False, **kw):
        super().__init__(**kw)
        if not ids:
            raise ValueError('No {self.service.item.type} ID(s) specified')

        self._get_comments = get_comments
        self._get_attachments = get_attachments
        self._get_changes = get_changes

        reqs = [self.service.GetItemRequest(ids=ids)]
        for call in ('comments', 'attachments', 'changes'):
            if getattr(self, f'_get_{call}'):
                reqs.append(getattr(self.service, f'{call.capitalize()}Request')(ids=ids))
            else:
                reqs.append(NullRequest())
        self._reqs = tuple(reqs)

    def parse(self, data):
        items, comments, attachments, changes = data
        for item in items:
            item.comments = next(comments)
            item.attachments = next(attachments)
            item.changes = next(changes)
            yield item
