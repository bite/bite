from urllib.parse import parse_qs, urlencode

from dateutil.parser import parse as parsetime
import lxml.html
import requests
from snakeoil.klass import steal_docs
from snakeoil.sequences import namedtuple

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

    class WebSession(Service.WebSession):

        def add_params(self, user, password):
            self.params.update({
                'Bugzilla_login': user,
                'Bugzilla_password': password,
            })

        def login(self):
            # extract auth token to bypass CSRF protection
            # https://bugzilla.mozilla.org/show_bug.cgi?id=713926
            auth_token_name = 'Bugzilla_login_token'
            r = self.session.get(self.service.base)
            doc = lxml.html.fromstring(r.text)
            token = doc.xpath(f'//input[@name="{auth_token_name}"]/@value')[0]
            if not token:
                raise BugzillaError(
                    'failed to extract login token, '
                    f'underlying token name may have changed from {auth_token_name}')

            # login via web form
            self.params[auth_token_name] = token
            r = self.session.post(self.service.base, data=self.params)
            # check that login was successful
            doc = lxml.html.fromstring(r.text)
            login_form = doc.xpath('//input[@name="Bugzilla_login"]')
            if login_form:
                raise AuthError('bad username or password')

            super().login()

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


class Bugzilla5_0(Bugzilla):
    """Generic bugzilla 5.0 service support."""

    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        self.apikeys = self.ApiKeys(self)
        self.saved_searches = self.SavedSearches(self)

    class ApiKeys(object):
        """Provide access to web service API keys."""

        _ApiKey = namedtuple("_ApiKey", ['key', 'desc', 'used', 'revoked'])

        def __init__(self, service):
            self._service = service
            self._userprefs_url = f"{self._service.base.rstrip('/')}/userprefs.cgi"
            self._doc = None

        @property
        def _keys(self):
            with self._service.web_session() as session:
                # get the apikeys page
                r = session.get(f'{self._userprefs_url}?tab=apikey')
                self._doc = lxml.html.fromstring(r.text)
                # verify API keys table still has the same id
                table = self._doc.xpath('//table[@id="email_prefs"]')
                if not table:
                    raise RequestError('failed to extract API keys table')

                # extract API key info from table
                apikeys = self._doc.xpath('//table[@id="email_prefs"]/tr/td[1]/text()')
                descriptions = self._doc.xpath('//table[@id="email_prefs"]/tr/td[2]/input/@value')
                last_used = self._doc.xpath('//table[@id="email_prefs"]/tr/td[3]//text()')
                revoked = self._doc.xpath('//table[@id="email_prefs"]/tr/td[4]/input')
                revoked = [bool(getattr(x, 'checked', False)) for x in revoked]

                existing_keys = []
                for desc, key, used, revoked in zip(descriptions, apikeys, last_used, revoked):
                    if used != 'never used':
                        used = parsetime(used)
                    existing_keys.append(self._ApiKey(key, desc, used, revoked))

            return existing_keys

        def __iter__(self):
            return iter(self._keys)

        def generate(self, description=None):
            """Generate API keys."""
            with self._service.web_session() as session:
                # check for existing keys with matching descriptions
                try:
                    match = next(k for k in self if k.desc == description)
                    if not self._service.client.confirm(
                            f'{description!r} key already exists, continue?'):
                        return
                except StopIteration:
                    pass

                params = {f'description_{i + 1}': x.desc for i, x in enumerate(self)}
                # add new key fields
                params.update({
                    'new_key': 'on',
                    'new_description': description,
                })

                r = session.post(self._userprefs_url, data=self._add_form_params(params))
                self._verify_changes(r)

        def _verify_changes(self, response):
            """Verify that apikey changes worked as expected."""
            doc = lxml.html.fromstring(response.text)
            msg = doc.xpath('//div[@id="message"]/text()')[0].strip()
            if msg != 'The changes to your api keys have been saved.':
                raise RequestError('failed generating apikey', text=msg)

        def _add_form_params(self, params):
            """Extract required token data from apikey generation form."""
            apikeys_form = self._doc.xpath('//form[@name="userprefsform"]/input')
            if not apikeys_form:
                raise BugzillaError('missing form data')
            for x in apikeys_form:
                params[x.name] = x.value
            return params

        def revoke(self, disable=(), enable=()):
            """Revoke and/or unrevoke API keys."""
            with self._service.web_session() as session:
                params = {}
                for i, x in enumerate(self):
                    params[f'description_{i + 1}'] = x.desc
                    if x.revoked:
                        if x.key in enable or x.desc in enable:
                            params[f'revoked_{i + 1}'] = 0
                        else:
                            # have to resubmit already revoked keys
                            params[f'revoked_{i + 1}'] = 1
                    if x.key in disable or x.desc in disable:
                        params[f'revoked_{i + 1}'] = 1

                r = session.post(self._userprefs_url, data=self._add_form_params(params))
                self._verify_changes(r)

    class SavedSearches(object):
        """Provide access to web service saved searches."""

        def __init__(self, service):
            self._service = service
            self._userprefs_url = f"{self._service.base.rstrip('/')}/userprefs.cgi"
            self._search_url = f"{self._service.base.rstrip('/')}/buglist.cgi"
            self._doc = None

        @property
        def _searches(self):
            with self._service.web_session() as session:
                # get the saved searches page
                r = session.get(f'{self._userprefs_url}?tab=saved-searches')
                self._doc = lxml.html.fromstring(r.text)

                existing_searches = {}

                # Scan for both personal and shared searches, personal searches
                # override shared if names collide.
                for table in ('shared_search_prefs', 'saved_search_prefs'):
                    # verify saved search table exists, shared searches might not
                    if (table == 'saved_search_prefs' and
                            not self._doc.xpath(f'//table[@id="{table}"]')):
                        raise RequestError('failed to extract saved search table')

                    # extract saved searches from tables
                    names = self._doc.xpath(f'//table[@id="{table}"]/tr/td[1]/text()')
                    forgets = [None] * len(names)
                    # determine the column number pull elements from it
                    edit_col_num = len(self._doc.xpath(
                        f'//table[@id="{table}"]/tr/th[.="Edit"][1]/preceding-sibling::th')) + 1
                    query_col = self._doc.xpath(
                        f'//table[@id="{table}"]/tr/td[{edit_col_num}]')
                    forget_col_num = len(self._doc.xpath(
                        f'//table[@id="{table}"]/tr/th[.="Forget"][1]/preceding-sibling::th')) + 1
                    forget_col = self._doc.xpath(
                        f'//table[@id="{table}"]/tr/td[{forget_col_num}]')

                    queries = []
                    for i, (q, f) in enumerate(zip(query_col, forget_col)):
                        try:
                            # find the query edit link
                            queries.append(next(q.iterlinks())[2])
                            forgets[i] = next(f.iterlinks())[2]
                        except StopIteration:
                            # skip searches that don't have advanced search edit links
                            # (usually only the default "My Bugs" search)
                            queries.append(None)
                            forgets[i] = None


                    for name, query, forget in zip(names, queries, forgets):
                        # skip the default "My Bugs" search which is uneditable
                        # and not removable
                        if query is None:
                            continue
                        if forget is not None:
                            forget = forget.split('?', 1)[1]
                        url_params = query.split('?', 1)[1]
                        existing_searches[name.strip()] = {
                            'params': parse_qs(url_params),
                            'forget': forget,
                        }

            return existing_searches

        def save(self, name, data):
            """Save a given search."""
            if isinstance(data, str):
                base, _url_params = data.split('?', 1)
                if base != self._search_url:
                    raise RequestError(f'invalid advanced search URL: {v!r}')
                search_url = data
            else:
                if not data:
                    raise RequestError('missing search parameters')
                search_url = f"{self._search_url}?{urlencode(data)}"

            with self._service.web_session() as session:
                r = session.get(search_url)
                doc = lxml.html.fromstring(r.text)

                # extract saved search form params
                save_search = doc.xpath(
                    '//div[@class="bz_query_remember"]/form/input[@type="hidden"]')
                if not save_search:
                    raise BugzillaError('missing save search option')

                params = {}
                for x in save_search:
                    params[x.name] = x.value
                params['newqueryname'] = name

                r = session.get(self._search_url, params=params)
                doc = lxml.html.fromstring(r.text)
                msg = doc.xpath('//div[@id="bugzilla-body"]/div//a/text()')
                if not msg or msg[0] != name:
                    raise RequestError(f'failed saving search: {name!r}')

        def remove(self, names):
            """Remove a given saved search."""
            searches = dict(self._searches.items())
            removals = []
            for name in names:
                search = searches.get(name, None)
                if search is None:
                    raise RequestError(f'nonexistent saved search: {name!r}')
                forget = search['forget']
                if forget is None:
                    raise RequestError(f'unable to remove saved search: {name!r}')
                removals.append(f"{self._search_url}?{forget}")

            # TODO: send these reqs in parallel
            with self._service.web_session() as session:
                for name, remove_url in zip(names, removals):
                    r = session.get(remove_url)
                    doc = lxml.html.fromstring(r.text)
                    msg = doc.xpath('//div[@id="bugzilla-body"]/div/b/text()')
                    if not msg or msg[0] != name:
                        raise RequestError(f'failed removing search: {name!r}')

        def __iter__(self):
            return iter(self._searches)

        def __contains__(self, name):
            return name in self._searches

        def get(self, name, default):
            return self._searches.get(name, default)

        def items(self):
            return self._searches.items()

        def keys(self):
            return self._searches.keys()

        def values(self):
            return self._searches.values()


class Bugzilla5_2(Bugzilla5_0):
    """Generic bugzilla 5.2 service support."""

    # setting auth tokens via headers is supported in >=bugzilla-5.1
    def inject_auth(self, request, params):
        if len(self.auth) > 16:
            self.session.headers['X-BUGZILLA-API-KEY'] = str(self.auth)
        else:
            self.session.headers['X-BUGZILLA-TOKEN'] = str(self.auth)
        self.authenticated = True
        return request, params
