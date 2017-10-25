# Support for the Google Code issue tracker
# https://chromium.googlesource.com/infra/infra/+/master/appengine/monorail/doc/api.md

from itertools import chain
import os
import re
import sys
from types import GeneratorType
from urllib.parse import urlparse

try: import simplejson as json
except ImportError: import json
from lxml import etree
import lxml.html
import requests
import xdg.Mime

from . import Service
from ..objects import decompress, Item, Comment, Attachment
from ..exceptions import RequestError, AuthError, BadAuthToken
from ..rfc3339 import parse_datetime as parsetime

class Monorail(Service):
    def __init__(self, service, **kw):
        self.headers = {}
        #self.headers = {'Accept': 'application/json', 'Content-Type': 'application/json'}
        super().__init__(service, **kw)
        self.item = 'issue'
        self.project_name = filter(None, self.base.split('/'))[-1]
        self.issues_url = 'https://code.google.com/feeds/issues/p/{}/issues/full'.format(self.project_name)
        self.comments_url = 'https://code.google.com/feeds/issues/p/{}/issues/{{}}/comments/full'.format(self.project_name)

    def login(self, user=None, password=None):
        """Authenticate a session."""
        super().login(user, password)

        # https://developers.google.com/accounts/docs/AuthForInstalledApps#Request
        if self.auth_token is None:
            params = {}
            params['Email'] = self.user
            params['Passwd'] = self.password
            params['service'] = 'code'
            params['source'] = 'bite-0.0.1'
            params['accountType'] = 'GOOGLE'

            url = 'https://www.google.com/accounts/ClientLogin'
            headers = {'Content-type': 'application/x-www-form-urlencoded'}
            content = self.request(url, headers=headers, data=params)

            for line in content.splitlines():
                if line.startswith('Auth='):
                    auth_token = 'GoogleLogin auth=' + line[5:]

        self.auth_token = auth_token

    def search(self, params=None, url=None):
        if url is None:
            params['alt'] = 'json'
            url = self.issues_url
        content = self.request(url=url, params=params)

        issues_json = json.loads(content, encoding='utf-8')
        results = issues_json['feed']['openSearch$totalResults']['$t']
        more = None

        if 'entry' in issues_json['feed']:
            for link in issues_json['feed']['link']:
                if link['rel'] == 'next':
                    more = link['href']
            return (self._issues(issues_json['feed']['entry']), results, more)

        else:
            return ([], results, more)

    def _issues(self, issues):
        for i in issues:
            issue = GooglecodeIssue()
            issue.id = i['issues$id']['$t']
            issue.title = i['title']['$t']
            issue.url = i['link'][1]['href']
            issue.reporter = i['author'][0]['name']['$t']
            issue.opened = parsetime(i['published']['$t'])
            issue.modified = parsetime(i['updated']['$t'])
            if 'issues$owner' in i:
                issue.owner = i['issues$owner']['issues$username']['$t']
            if 'issues$status' in i:
                issue.status = i['issues$status']['$t']
            issue.state = i['issues$state']['$t']
            issue.stars = i['issues$stars']['$t']
            yield issue

    def get(self, ids, get_comments=False, get_attachments=False, **kw):
        """Return an issue object given the issue id"""
        params = {'alt': 'json'}

        for id in ids:
            params['id'] = id
            issue_content = self.request(self.issues_url, params=params)
            issue_json = json.loads(issue_content, encoding='utf-8')
            issue_dict = issue_json['feed']['entry'][0]

            issue = GooglecodeIssue()
            issue.id = issue_dict['issues$id']['$t']
            issue.title = issue_dict['title']['$t']
            issue.url = issue_dict['link'][1]['href']
            issue.reporter = issue_dict['author'][0]['name']['$t']
            issue.opened = parsetime(issue_dict['published']['$t'])
            issue.modified = parsetime(issue_dict['updated']['$t'])
            if 'issues$owner' in issue_dict:
                issue.owner = issue_dict['issues$owner']['issues$username']['$t']
            else:
                issue.owner = 'None'
            if 'issues$status' in issue_dict:
                issue.status = issue_dict['issues$status']['$t']
            else:
                issue.status = 'None'
            issue.state = issue_dict['issues$state']['$t']
            issue.stars = issue_dict['issues$stars']['$t']

            issue.cc = self._cc(issue_dict)
            issue.labels = self._labels(issue_dict)

            issue.comments = None
            if get_comments:

                # The initial report is comment #0
                i = 0
                creator = issue.reporter
                date = issue.opened
                content = lxml.html.fromstring(issue_dict['content']['$t'].strip()).text_content()
                initial = [GooglecodeComment(count=i, creator=creator, date=date, text=content)]

                comments = self.get_comments(id)
                issue.comments = chain(initial, comments)

            # Blockers don't get updated when issues are closed
            # so we parse the webpage instead
            #if 'issues$blockedOn' in issue_dict:
            #    blocks = []
            #    for blocker in issue_dict['issues$blockedOn']:
            #        blocks.append(blocker['issues$id']['$t'])
            #    issue.blocks = blocks

            if get_attachments:
                (issue.attachments, issue.blocks, issue.depends) = self._parse_webpage(issue.id)

            yield issue

    def get_comments(self, id):
        url = self.comments_url.format(id)
        params = {'alt': 'json'}
        params['max-results'] = 1000
        data = self.request(url, params=params)
        comments = json.loads(data)['feed']

        if 'entry' in comments:
            for c in comments['entry']:
                id = int(c['id']['$t'].split('/')[-1])
                creator = c['author'][0]['name']['$t']
                date = parsetime(c['updated']['$t'])
                text = c['content']['$t'].strip()
                updates = self._parse_updates(c['issues$updates'])
                if updates is not None:
                    changes = {'updates': updates}
                else:
                    changes = None
                yield GooglecodeComment(count=id, creator=creator, date=date, text=text, changes=changes)

    def request(self, url, headers=None, params=None, data=None):
        """Attempt to call method with params. Log in if authentication is required."""
        self.headers['Authorization'] = self.auth_token
        if headers is not None:
            headers = dict(self.headers.items() + headers.items())
        else:
            headers = self.headers

        if data is not None:
            r = self.session.post(url=url, params=params, data=data, headers=headers, verify=self.verify, stream=True)
        else:
            r = self.session.get(url=url, params=params, data=data, headers=headers, verify=self.verify, stream=True)

        if r.status_code == requests.codes.ok:
            return r.content
        else:
            if r.status_code == 404:
                raise RequestError(msg='Project not found')
            else:
                raise RequestError(msg=r.reason, code=r.status_code)
        #elif r.status_code == 401 and (r.reason == 'Token invalid' or r.reason == 'Token expired'):
        #    raise BadAuthToken(r.reason)
        #elif r.status_code == 403 and r.reason == 'Error=BadAuthentication':
        #    raise RequestError('Incorrect username or password')
        #else:
        #    raise RequestError(r.reason)

    def _cc(self, issue):
        if 'issues$cc' in issue:
            for cc in issue['issues$cc']:
                yield cc['issues$username']['$t']

    def _labels(self, issue):
        if 'issues$label' in issue:
            for label in issue['issues$label']:
                yield label['$t']

    def _parse_webpage(self, id, get_data=False):
        if isinstance(id, str):
            id, i = id.split('-')

        attachments = []
        url = 'https://code.google.com/p/{}/issues/detail?id={}'.format(self.project_name, id)
        content = self.request(url)
        tree = etree.HTML(content)
        for j, a in enumerate(tree.xpath('//div[@class="attachments"]/table/tr/td[2]')):
            if isinstance(id, str) and int(i) != j:
                # skip unrequested attachments if the caller function is attachments
                continue

            size = a.find('br').tail.strip()
            name = a.findtext('b')
            try:
                link = a.find('a[2]').attrib['href']
            except:
                # Binary files don't have a view link
                link = a.find('a[1]').attrib['href']

            # google code uses relative links with no protocols
            if urlparse(link).scheme == '':
                link = 'https:{}'.format(link)

            mimetype = str(xdg.Mime.get_type_by_name(link.split('&')[1]))

            if get_data:
                data = self.request(link)
            else:
                data = None

            attachments.append(Attachment(id='%s-%s' % (id, j), filename=name, url=link,
                                          size=size, mimetype=mimetype, data=data))

        blocks = []
        depends = []
        for b in tree.xpath('//div[@class="rel_issues"]/a'):
            if not b.attrib.get('class') == 'closed_ref':
                issue_type = b.itersiblings(tag='b', preceding=True).next().text
                issue = b.attrib['href'].split('=')[-1]
                if issue_type == 'Blocked on:':
                    depends.append(int(issue))
                elif issue_type == 'Blocking:':
                    blocks.append(int(issue))

        return (attachments, blocks, depends)

    def get_attachment(self, ids):
        # TODO: don't call _parse_webpage multiple times for the same issue ID
        for id in ids:
            (attachments, _, _) = self._parse_webpage(id, get_data=True)
            if not attachments:
                raise RequestError("The attachment {} doesn't exist.".format(id))
            for attachment in attachments:
                yield attachment

    def _parse_updates(self, updates):
        u = {}
        for k, v in updates.iteritems():
            if k.startswith('issues$'): k = k[7:] # strip off issues$ prefix
            if k.endswith('Update'): k = k[:-6] # strip off Update suffix
            k = k.capitalize()
            if isinstance(v, list):
                u[k] = [j['$t'] for j in v]
            elif isinstance(v, dict):
                u[k] = v['$t']
        if u:
            return u
        else:
            return None

class GooglecodeIssue(Item):
    attributes = {
        #'cc': 'CC',
        #'label': 'Labels',
        #'summary': 'Summary',
        #'updates': 'Updates',

        # available via search
        'id': 'ID',
        'title': 'Title',
        'url': 'URL',
        'reporter': 'Reporter',
        'opened': 'Opened',
        'modified': 'Updated',
        'owner': 'Owner',
        'status': 'Status',
        'state': 'State',
        'stars': 'Stars',
    }

    attribute_aliases = {
        'created': 'opened',
    }

    def __init__(self, labels=None, stars=0, state=None, **kw):
        self.labels = labels
        self.stars = stars
        self.state = state
        super().__init__(**kw)

    def __str__(self):
        lines = []
        print_fields = [
            ('title', 'Title'),
            ('reporter', 'Reporter'),
            ('opened', 'Reported'),
            ('modified', 'Updated'),
            ('owner', 'Owner'),
            ('status', 'Status'),
            ('state', 'State'),
            ('stars', 'Stars'),
            ('cc', 'CC'),
            ('blocks', 'Blocks'),
            ('depends', 'Depends'),
            ('labels', 'Labels'),
            ('url', 'URL'),
        ]

        for field, title in print_fields:
            value = getattr(self, field)

            if field == 'labels':
                attr = re.compile(r'^(.+)-(.+)$')
                for label in value:
                    x = attr.match(label)
                    if x:
                        lines.append('{:<12}: {}'.format(x.group(1), x.group(2)))
                    else:
                        lines.append('{:<12}: {}'.format('Label', label))
                continue

            if isinstance(value, list) or isinstance(value, GeneratorType):
                value = ', '.join(map(str, value))

            if not value:
                continue
            else:
                lines.append('{:<12}: {}'.format(title, value))

        return '\n'.join(lines)


class GooglecodeComment(Comment):
    def __init__(self, id=None, creator=None, date=None, count=None, changes=None, text=None, **kw):
        if not text:
            text = '(No comment was entered for this change)'
        super().__init__(id, creator, date, count, changes, text)
