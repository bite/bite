try: import simplejson as json
except ImportError: import json
import ijson
import requests

from . import Bugzilla, BugzillaAttachment, BugzillaComment, BugzillaEvent
from ...exceptions import RequestError

class BugzillaRest(Bugzilla):
    def __init__(self, **kw):
        base = kw['base']
        if base.split('/')[-1] == '':
            kw['base'] = base[:-1]

        self.auth = None
        self.headers = {
            'Accept': 'application/json',
            'Content-Type': 'application/json'
        }

        super().__init__(**kw)
        self.bug = RestBug

    def login(self):
        if self.auth_token:
            for cookie in self.auth_token:
                if cookie.name == 'Bugzilla_login':
                    login = cookie.value
                elif cookie.name == 'Bugzilla_logincookie':
                    logincookie = cookie.value
            self.auth = {'userid': login, 'cookie': logincookie}
        else:
            self.auth = {'username': self.user, 'password': self.password}

    def search(self, params):
        url = '{}/bug'.format(self.base)
        data = self.request(url, params, iter_content=True)
        bugs = ijson.items(data, 'bugs.item')
        return (RestBug(x) for x in bugs)

    def get_comments(self, bug_id):
        url = '{}/bug/{}/comment'.format(self.base, bug_id)
        data = self.request(url)
        return [BugzillaComment(x, i, rest=True) for i, x in enumerate(data['comments'])]

    def get_attachment(self, attachment_id):
        for a in attachment_id:
            url = '{}/attachment/{}'.format(self.base, a)
            args = {'attachmentdata': 1}
            data = self.request(url, params=args)
            yield BugzillaAttachment(data)

    def get_attachments(self, bug_id):
        url = '{}/bug/{}/attachment'.format(self.base, bug_id)
        data = self.request(url)
        return [BugzillaAttachment(x) for x in data['attachments']]

    def get_history(self, bug_id):
        url = '{}/bug/{}/history'.format(self.base, bug_id)
        data = self.request(url)
        return [BugzillaEvent(x, i, rest=True) for i, x in enumerate(data['history'], start=1)]

    def get(self, bug_id, get_comments, get_attachments, get_history, **kw):
        """Return bug object(s) given the bug id(s)"""
        include_fields = ['_default,blocks,cc,depends_on,dupe_of,flags,groups,see_also']

        if get_attachments:
            include_fields.append('attachments')
        if get_comments:
            include_fields.append('comments')
        if get_history:
            include_fields.append('history')

        params = {'id': bug_id, 'include_fields': [','.join(include_fields)]}
        url = '{}/bug'.format(self.base)
        data = self.request(url, params)

        if data['bugs']:
            bugs = data['bugs']
        else:
            raise RequestError('You are not authorized to access bug #{}'.format(bug_id))

        for bug in bugs:
            attachments = []
            comments = []
            history = []
            if get_attachments and bug['attachments']:
                attachments = [BugzillaAttachment(x) for x in bug['attachments']]
            if get_comments and bug['comments']:
                comments = [BugzillaComment(x, i, rest=True) for i, x in enumerate(bug['comments'])]
            if get_history and bug['history']:
                history = [BugzillaEvent(x, i, rest=True) for i, x in enumerate(bug['history'], start=1)]

            yield RestBug(bug, comments, attachments, history)

    def request(self, url, params=None, data=None, iter_content=False):
        """Attempt to call method with args. Log in if authentication is required."""

        if self.auth is not None:
            params.update(self.auth)

        try:
            if data is None:
                r = self.session.get(url=url, params=params, **self.requests_params)
            else:
                r = self.session.post(url=url, params=params, data=data, **self.requests_params)
        except:
            raise

        # TODO: test for returned API Errors
        if r.status_code == requests.codes.ok:
            if iter_content:
                return IterContent(r)
            else:
                return r.json()
        else:
            raise RequestError(msg=r.reason, code=r.status_code)

class IterContent(object):
    def __init__(self, file, size=64*1024):
        self.chunks = file.iter_content(chunk_size=size)

    def read(self, size=64*1024):
        return next(self.chunks)

class RestBug(Item):
    def __init__(self, bug, comments=None, attachments=None, history=None, **kw):
        for k, v in bug.items():
            try:
                if not v or v == '---':
                    # skip empty lists and blank fields
                    continue
                elif k in ['assigned_to', 'creator', 'qa_contact']:
                    if 'real_name' in v:
                        setattr(self, k, '{} ({})'.format(v['real_name'], v['name']))
                    else:
                        if v['name']:
                            setattr(self, k, v['name'])
                elif k == 'cc':
                    self.cc = [cc['name'] for cc in bug['cc']]
                elif k == 'flags':
                    self.flags = [flag['name'] for flag in bug['flags']]
                else:
                    if isinstance(v, str) and re.match(r'^\d\d\d\d-\d\d-\d\dT\d\d:\d\d:\d\dZ$', v):
                        setattr(self, k, parsetime(v))
                    else:
                        setattr(self, k, v)
            except (KeyError, AttributeError):
                continue

        self.attachments = attachments
        self.comments = comments
        self.history = history

    def __str__(self):
        lines = []
        print_fields = (
            ('summary', 'Title'),
            ('alias', 'Alias'),
            ('assigned_to', 'Assignee'),
            ('creator', 'Reporter'),
            ('qa_contact', 'QA Contact'),
            ('creation_time', 'Reported'),
            ('last_change_time', 'Updated'),
            ('status', 'Status'),
            ('resolution', 'Resolution'),
            ('dupe_of', 'Duplicate'),
            ('whiteboard', 'Whiteboard'),
            ('severity', 'Severity'),
            ('priority', 'Priority'),
            ('classification', 'Class'),
            ('product', 'Product'),
            ('component', 'Component'),
            ('platform', 'Platform'),
            ('op_sys', 'OS'),
            ('keywords', 'Keywords'),
            ('target_milestone', 'Target'),
            ('version', 'Version'),
            ('url', 'URL'),
            ('ref', 'Reference'),
            ('see_also', 'See also'),
            ('cc', 'CC'),
            ('blocks', 'Blocks'),
            ('depends_on', 'Depends'),
            ('flags', 'Flags'),
            ('groups', 'Groups'),
            ('estimated_time', 'Estimated'),
            ('deadline', 'Deadline'),
            ('actual_time', 'Actual'),
            ('remaining_time', 'Remaining'),
            #('id', 'ID'),
            #('is_cc_accessible', 'Is CC Accessible'),
            #('is_confirmed', 'Confirmed'),
            #('is_creator_accessible', 'Is Creator Accessible'),
            #('history', 'History'),
            #('attachments', 'Attachments'),
            #('comments', 'Comments'),
        )

        for field, title in print_fields:
            try:
                value = getattr(self, field)
            except AttributeError:
                continue

            values = value
            if isinstance(value, list):
                values = ', '.join(map(str, value))
            else:
                values = value
            lines.append('{:<12}: {}'.format(title, values))

        custom_fields = ((k, v) for (k, v) in vars(self).items()
                         if re.match(r'^cf_\w+$', k))
        for k, v in custom_fields:
            title = string.capwords(k[3:], '_')
            title = title.replace('_', ' ')
            lines.append('{:<12}: {}'.format(title, v))

        return '\n'.join(lines)
