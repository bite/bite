from snakeoil.klass import steal_docs

from .objects import BugzillaBug, BugzillaAttachment
from .. import Service
from ...cache import Cache, csv2tuple
from ...exceptions import RequestError, AuthError


class BugzillaError(RequestError):
    """Bugzilla service specific error."""

    def __init__(self, msg, code=None, text=None):
        msg = 'Bugzilla error: ' + msg
        super().__init__(msg, code, text)


class BugzillaCache(Cache):

    def __init__(self, *args, **kw):
        # default to bugzilla-5 open/closed statuses
        defaults = {
            'open_status': ('CONFIRMED', 'IN_PROGRESS', 'UNCONFIRMED'),
            'closed_status': ('RESOLVED', 'VERIFIED'),
        }

        converters = {
            'open_status': csv2tuple,
            'closed_status': csv2tuple,
        }

        super().__init__(defaults=defaults, converters=converters, *args, **kw)


class Bugzilla(Service):
    """Generic bugzilla service support."""

    _cache_cls = BugzillaCache

    item = BugzillaBug
    item_endpoint = '/show_bug.cgi?id='
    attachment = BugzillaAttachment
    attachment_endpoint = '/attachment.cgi?id='

    def __init__(self, max_results=None, *args, **kw):
        # most bugzilla instances default to 10k results per req
        if max_results is None:
            max_results = 10000
        super().__init__(*args, max_results=max_results, **kw)

    @property
    def cache_updates(self):
        """Pull latest data from service for cache update."""
        config_updates = {}
        reqs = []

        # get open/closed status values
        reqs.append(self.FieldsRequest(names=['bug_status']))
        # get available products
        reqs.append(self.ProductsRequest())
        # get server bugzilla version
        reqs.append(self.VersionRequest())

        statuses, products, version = self.send(reqs)

        open_status = []
        closed_status = []
        for status in statuses[0].get('values', []):
            if status.get('name', None) is not None:
                if status.get('is_open', False):
                    open_status.append(status['name'])
                else:
                    closed_status.append(status['name'])
        products = [d['name'] for d in sorted(products, key=lambda x: x['id']) if d['is_active']]
        config_updates['open_status'] = tuple(sorted(open_status))
        config_updates['closed_status'] = tuple(sorted(closed_status))
        config_updates['products'] = tuple(products)
        config_updates['version'] = version

        return config_updates

    @steal_docs(Service)
    def login(self, user, password, restrict_login=False, **kw):
        super().login(user, password, restrict_login=restrict_login)

    @steal_docs(Service)
    def inject_auth(self, request, params):
        if params is None:
            params = {}
        # TODO: Is there a better way to determine the difference between
        # tokens and API keys?
        if len(self.auth) > 16:
            params['Bugzilla_api_key'] = str(self.auth)
        else:
            params['Bugzilla_token'] = str(self.auth)
        return request, params

    @staticmethod
    def handle_error(code, msg):
        """Handle bugzilla specific errors.

        Bugzilla web service error codes and their descriptions can be found at:
        https://github.com/bugzilla/bugzilla/blob/5.0/Bugzilla/WebService/Constants.pm#L56
        """
        # (-+)32000: fallback error code for unmapped/unknown errors, negative
        # is fatal and positive is transient
        if code == 32000:
            if 'expired' in msg:
                # assume the auth token has expired
                raise AuthError(msg, expired=True)
        # 102: bug access or query denied due to insufficient permissions
        # 410: login required to perform this request
        elif code in (102, 410):
            raise AuthError(msg=msg)
        raise BugzillaError(msg=msg, code=code)

    def _failed_http_response(self, response):
        if response.status_code in (401, 403):
            data = self.parse_response(response)
            raise AuthError(f"authentication failed: {data.get('message', '')}")
        else:
            super()._failed_http_response(response)


class Bugzilla5_2(Bugzilla):
    """Generic bugzilla 5.2 service support."""

    # setting auth tokens via headers is supported in >=bugzilla-5.1
    def inject_auth(self, request, params):
        if len(self.auth) > 16:
            self.session.headers['X-BUGZILLA-API-KEY'] = str(self.auth)
        else:
            self.session.headers['X-BUGZILLA-TOKEN'] = str(self.auth)
        self.authenticated = True
        return request, params
