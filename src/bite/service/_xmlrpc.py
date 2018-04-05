from xmlrpc.client import dumps, loads

from ._xml import LxmlXml


class Xmlrpc(LxmlXml):
    """Support generic XML-RPC services."""

    @staticmethod
    def _encode_request(method, params=None):
        """Encode the data body for an XML-RPC request."""
        encoding = 'utf-8'
        if isinstance(params, list):
            params = tuple(params)
        else:
            params = (params,) if params is not None else ()
        return dumps(params, method, encoding=encoding,
                     allow_none=True).encode(encoding, 'xmlcharrefreplace')

    @staticmethod
    def _decode_request(request):
        """Decode the data body of a request."""
        params, method = loads(request.data)
        if not params:
            params = None
        else:
            params = params[0]
        return method, params
