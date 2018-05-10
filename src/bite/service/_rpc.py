from itertools import repeat, islice

from . import Service
from ._reqs import Request
from ..utils import nonstring_iterable


class Rpc(Service):

    _multicall_method = 'method'
    _multicall_iter = None

    @staticmethod
    def _extract_params(params):
        return params

    @staticmethod
    def _encode_params(params):
        return params

    def multicall(self, *args, **kw):
        return Multicall(service=self, *args, **kw)

    def merged_multicall(self, reqs, *args, **kw):
        return MergedMulticall(reqs=reqs, service=self, *args, **kw)


class RPCRequest(Request):
    """Construct an RPC request."""

    def __init__(self, method, **kw):
        super().__init__(method='POST', **kw)
        self.method = method

    def _finalize(self):
        """Encode the data body of the request."""
        super()._finalize()
        params = self.params if self.params else None
        self._req.data = self.service._encode_request(self.method, params)


class Multicall(RPCRequest):
    """Construct a system.multicall request."""

    def __init__(self, method, params, service, *args, **kw):
        methods = repeat(method) if isinstance(method, str) else method
        params = (tuple(x) if nonstring_iterable(x) else (x,) for x in params)
        params = tuple(
            {service._multicall_method: m, 'params': x} for m, x in zip(methods, params))
        super().__init__(
            *args, service=service, method='system.multicall',
            params=service._encode_params(params), **kw)

    def parse(self, data):
        return self.service._multicall_iter(data)


class MergedMulticall(RPCRequest):

    def __init__(self, reqs, service, *args, **kw):
        self.req_groups = []
        self.reqs = reqs

        params = []
        for req in reqs:
            req_params = service._extract_params(req.params)
            if req_params:
                params.extend(req_params)
            self.req_groups.append(len(req_params))
        params = tuple(params)

        super().__init__(
            *args, service=service, method='system.multicall',
            params=service._encode_params(params), **kw)

    def parse(self, data):
        start = 0
        for i, length in enumerate(self.req_groups):
            if length == 0:
                yield None
            else:
                yield self.reqs[i].parse(islice(data, start, start + length))
                start += length
