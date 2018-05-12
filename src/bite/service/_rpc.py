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

    def __init__(self, method, *args, **kw):
        self.methods = method
        super().__init__(*args, method='system.multicall', **kw)

    def _finalize(self):
        methods = repeat(self.methods) if isinstance(self.methods, str) else self.methods
        self.params = (tuple(x) if nonstring_iterable(x) else (x,) for x in self.params)
        self.params = tuple(
            {self.service._multicall_method: m, 'params': x} for m, x in zip(methods, self.params))
        self.params = self.service._encode_params(self.params)
        super()._finalize()

    def parse(self, data):
        return self.service._multicall_iter(data)


class MergedMulticall(RPCRequest):

    def __init__(self, reqs, *args, **kw):
        self.req_groups = []
        self.reqs = reqs
        super().__init__(*args, method='system.multicall', **kw)

    def _finalize(self):
        params = []
        for req in self.reqs:
            req._finalize()
            req_params = self.service._extract_params(req.params)
            if req_params:
                params.extend(req_params)
            self.req_groups.append(len(req_params))
        self.params = self.service._encode_params(tuple(params))
        super()._finalize()

    def parse(self, data):
        start = 0
        for i, length in enumerate(self.req_groups):
            if length == 0:
                yield None
            else:
                yield from self.reqs[i].parse(islice(data, start, start + length))
                start += length
