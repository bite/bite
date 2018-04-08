from xmlrpc.client import dumps, loads, Fault

from ._xml import LxmlXml
from ..exceptions import RequestError


class Xmlrpc(LxmlXml):
    """Support generic XML-RPC services.
    
    Spec: http://xmlrpc.scripting.com/spec.html
    """

    @staticmethod
    def _encode_request(method, params=None):
        encoding = 'utf-8'
        if isinstance(params, list):
            params = tuple(params)
        else:
            params = (params,) if params is not None else ()
        return dumps(params, method, encoding=encoding,
                     allow_none=True).encode(encoding, 'xmlcharrefreplace')

    @staticmethod
    def _decode_request(request):
        params, method = loads(request.data)
        if not params:
            params = None
        else:
            params = params[0]
        return method, params

    def parse_response(self, response):
        try:
            data = super().parse_response(response)
        except Fault as e:
            raise RequestError(msg=e.faultString, code=e.faultCode)

        faults = data.get('faults', None)
        if not faults:
            return data
        else:
            self.handle_error(code=faults[0]['faultCode'], msg=faults[0]['faultString'])
