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

    def multicall(self, **kw):
        return Multicall(service=self, **kw)

    def merged_multicall(self, *, reqs, **kw):
        return MergedMulticall(reqs=reqs, service=self, **kw)


class RPCRequest(Request):
    """Construct an RPC request."""

    def __init__(self, *, command, **kw):
        super().__init__(method='POST', **kw)
        self.command = command

    def _finalize(self):
        """Encode the data body of the request."""
        super()._finalize()
        params = self.params if self.params else None
        self._req.data = self.service._encode_request(self.command, params)


class Multicall(RPCRequest):
    """Construct a system.multicall request."""

    def __init__(self, *, command, **kw):
        self.commands = command
        super().__init__(command='system.multicall', **kw)

    def _finalize(self):
        commands = repeat(self.commands) if isinstance(self.commands, str) else self.commands
        self.params = (tuple(p) if nonstring_iterable(p) else (p,) for p in self.params)
        self.params = tuple(
            {self.service._multicall_method: c, 'params': p} for c, p in zip(commands, self.params))
        self.params = self.service._encode_params(self.params)
        super()._finalize()

    def parse(self, data):
        return self.service._multicall_iter(data)


class MergedMulticall(RPCRequest):

    def __init__(self, reqs=None, **kw):
        self.req_groups = []
        self.reqs = reqs
        super().__init__(command='system.multicall', **kw)

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
            yield self.reqs[i].parse(islice(data, start, start + length))
            start += length
