import base64
from http.cookiejar import LWPCookieJar
import os
import re
import stat
import subprocess
import sys
from collections import defaultdict
from itertools import chain, groupby

from dateutil.parser import parse as parsetime

from bite.utils import block_edit, confirm, get_input
from bite.cli import Cli
from bite.exceptions import CliError
from bite.utc import utc

class Bugzilla(Cli):
    def __init__(self, **kw):
        super(Bugzilla, self).__init__(**kw)

    def _attach_params(self, **kw):
        if kw['comment'] is None:
            kw['comment'] = block_edit('Enter optional long description of attachment')
        return kw

    def _create_params(self, batch, **kw):
        # load description from file or stdin
        if kw['description_from']:
            try:
                if kw['description_from'] == '-':
                    kw['description'] = sys.stdin.read()
                else:
                    kw['description'] = open(kw['description_from'], 'r').read()
            except IOError as e:
                raise CliError('Unable to read file: {}: {}'.format(kw['description_from'], e))

        if not batch:
            self.log('Press Ctrl+C at any time to abort.')

            if not kw['product']:
                while not kw['product'] or len(kw['product']) < 1:
                    kw['product'] = get_input('Enter product: ')
            else:
                self.log('Enter product: {}'.format(kw['product']))

            if not kw['component']:
                while not kw['component'] or len(kw['component']) < 1:
                    kw['component'] = get_input('Enter component: ')
            else:
                self.log('Enter component: {}'.format(kw['component']))

            if not kw['version']:
                # Try to get the default version for the entered product by
                # naively assuming it has the highest ID
                params = {'names': [kw['product']], 'include_fields': ['versions']}
                r = self.service.query('Product.get', params)
                if r['products']:
                    default_version = r['products'][0]['versions'][-1]['name']
                else:
                    raise CliError('Product "{}" not found'.format(kw['product']))

                line = get_input('Enter version (default: {}): '.format(default_version))
                if len(line):
                    kw['version'] = line
                else:
                    kw['version'] = default_version
            else:
                self.log('Enter version: {}'.format(kw['version']))

            if not kw['summary']:
                while not kw['summary'] or len(kw['summary']) < 1:
                    kw['summary'] = get_input('Enter title: ')
            else:
                self.log('Enter title: {}'.format(kw['summary']))

            if not kw['description']:
                line = block_edit('Enter bug description: ')
                if len(line):
                    kw['description'] = line
            else:
                self.log('Enter bug description: {}'.format(kw['description']))

            if not kw['op_sys']:
                op_sys_msg = 'Enter operating system where this bug occurs: '
                line = get_input(op_sys_msg)
                if len(line):
                    kw['op_sys'] = line
            else:
                self.log('Enter operating system: {}'.format(kw['op_sys']))

            if not kw['platform']:
                platform_msg = 'Enter hardware platform where this bug occurs: '
                line = get_input(platform_msg)
                if len(line):
                    kw['platform'] = line
            else:
                self.log('Enter hardware platform: {}'.format(kw['platform']))

            if kw['priority'] is None:
                priority_msg = 'Enter priority (e.g. normal) (optional): '
                line = get_input(priority_msg)
                if len(line):
                    kw['priority'] = line
            else:
                self.log('Enter priority (optional): {}'.format(kw['priority']))

            if kw['severity'] is None:
                severity_msg = 'Enter severity (e.g. normal) (optional): '
                line = get_input(severity_msg)
                if len(line):
                    kw['severity'] = line
            else:
                self.log('Enter severity (optional): {}'.format(kw['severity']))

            if kw['target_milestone'] is None:
                milestone_msg = 'Enter target milestone (optional): '
                line = get_input(milestone_msg)
                if len(line):
                    kw['target_milestone'] = line
            else:
                self.log('Enter target milestone (optional): {}'.format(kw['target_milestone']))

            if kw['alias'] is None:
                alias_msg = 'Enter alias (optional): '
                line = get_input(alias_msg)
                if len(line):
                    kw['alias'] = line
            else:
                self.log('Enter alias (optional): {}'.format(kw['alias']))

            if kw['assigned_to'] is None:
                assign_msg = 'Enter assignee (e.g. dev@email.com) (optional): '
                line = get_input(assign_msg)
                if len(line):
                    kw['assigned_to'] = line
            else:
                self.log('Enter assignee (optional): {}'.format(kw['assigned_to']))

            if kw['status'] is None:
                status_msg = 'Enter status (optional): '
                line = get_input(status_msg)
                if len(line):
                    kw['status'] = line
            else:
                self.log('Enter status (optional): {}'.format(kw['status']))

            if kw['cc'] is None:
                cc_msg = 'Enter CCs (comma separated) (optional): '
                line = get_input(cc_msg)
                if len(line):
                    kw['cc'] = line.split(',')
            else:
                self.log('Enter CCs (optional): {}'.format(', '.join(kw['cc'])))

            # the API doesn't support setting keywords while creating a bug
            #if kw['keywords'] is None:
            #    keywords_msg = 'Enter keywords (comma separated) (optional): '
            #    line = get_input(keywords_msg)
            #    if len(line):
            #        kw['keywords'] = line.split(',')
            #else:
            #    self.log('Enter keywords (optional): {}'.format(', '.join(kw['keywords'])))

            if kw['groups'] is None:
                groups_msg = 'Enter groups (comma separated) (optional): '
                line = get_input(groups_msg)
                if len(line):
                    kw['groups'] = line.split(',')
            else:
                self.log('Enter groups (optional): {}'.format(', '.join(kw['groups'])))

            if kw['append_command'] is None:
                kw['append_command'] = get_input('Append the output of the following command (leave blank for none): ')
            else:
                self.log('Append command (optional): {}'.format(kw['append_command']))

        # append the output from append_command to the description
        if kw['append_command'] is not None and kw['append_command'] != '':
            append_command_output = subprocess.check_output(kw['append_command'])
            kw['description'] = kw['description'] + '\n\n' + '$ ' + kw['append_command'] + '\n' + append_command_output

        options_log = []
        options_log.append('=' * self.columns)
        options_log.append('{:<12}: {}'.format('Product', kw['product']))
        options_log.append('{:<12}: {}'.format('Component', kw['component']))
        options_log.append('{:<12}: {}'.format('Version', kw['version']))
        options_log.append('{:<12}: {}'.format('Title', kw['summary']))
        options_log.append('{:<12}: {}'.format('OS', kw['op_sys']))
        options_log.append('{:<12}: {}'.format('Platform', kw['platform']))
        options_log.append('{:<12}: {}'.format('Priority', kw['priority']))
        options_log.append('{:<12}: {}'.format('Severity', kw['severity']))
        if kw['target_milestone'] is not None:
            options_log.append('{:<12}: {}'.format('Milestone', kw['target_milestone']))
        if kw['alias'] is not None:
            options_log.append('{:<12}: {}'.format('Alias', kw['alias']))
        if kw['assigned_to'] is not None:
            options_log.append('{:<12}: {}'.format('Assigned to', self.service._desuffix(kw['assigned_to'])))
            # add potentially missing domain suffix
            kw['assigned_to'] = self.service._resuffix(kw['assigned_to'])
        if kw['status'] is not None:
            options_log.append('{:<12}: {}'.format('Status', kw['status']))
        if kw['cc'] is not None:
            options_log.append('{:<12}: {}'.format('CC', ', '.join(map(self.service._desuffix, kw['cc']))))
            # add potentially missing domain suffixes
            kw['cc'] = list(map(self.service._resuffix, kw['cc']))
        #if kw['keywords'] is not None:
        #    options_log.append('{:<12}: {}'.format('Keywords', ', '.join(kw['keywords'])))
        if kw['groups'] is not None:
            options_log.append('{:<12}: {}'.format('Groups', ', '.join(kw['groups'])))
        options_log.append(self._header('-', 'Description'))
        if kw['description'] is not None:
            # interpret backslash escapes
            kw['description'] = kw['description'].decode('string_escape')
            options_log.append('{}'.format(kw['description']))
        options_log.append('=' * self.columns)

        return (options_log, kw)

    def _modify_params(self, **kw):
        if kw['reply']:
            raise NotImplementedError()
            # get comment kw['reply']
            #kw['comment-body'] = block_edit('Enter comment:').rstrip()

        if kw['comment_from']:
            try:
                if kw['comment_from'] == '-':
                    kw['comment-body'] = sys.stdin.read()
                else:
                    kw['comment-body'] = open(kw['comment_from'], 'r').read()
            except IOError as e:
                raise CliError('Unable to read file: {}: {}'.format(kw['comment_from'], e))

        if kw['comment_editor']:
            kw['comment-body'] = block_edit('Enter comment:').rstrip()

        return kw

    def print_changes(self, bugs, params):
        for bug in bugs:
            print(self._header('=', 'Bug: {}'.format(str(bug['id']))))
            changes = bug['changes']

            if len(changes):
                print(self._header('-', 'Modified fields'))
                for k, v in changes.items():
                    try:
                        field = self.service.attributes[k]
                    except KeyError:
                        field = k

                    if v['removed'] and v['added']:
                        print('{}: {} -> {}'.format(field, v['removed'], v['added']))
                    else:
                        if v['removed']:
                            print('{}: -{}'.format(field, v['removed']))
                        elif v['added']:
                            print('{}: +{}'.format(field, v['added']))
            else:
                if 'comment-body' not in params:
                    print('No changes made')

            if 'comment-body' in params and params['comment-body'] is not None:
                print(self._header('-', 'Added comment'))
                print(params['comment-body'])

    def query(self, raw, **kw):
        if kw['queries']:
            if len(kw['queries']) == 0:
                raise CliError('Please specify a query')
            for query in kw['queries']:
                q = query.split('#')
                self.log('Executing query: {}'.format(q[0]))
                params = None
                if len(q) > 1:
                    self.log('Parameters: {}'.format(q[1]))
                    try:
                        params = json.loads(q[1])
                    except SyntaxError as e:
                        raise
                result = self.service.query(method=q[0], params=params)
                if not raw:
                    print(json.dumps(result, indent=2))
                else:
                    print(json.dumps(result))

        if kw['bugzilla_version']:
            version = self.service.version()
            print('Bugzilla version: {}'.format(version))

        if kw['bugzilla_extensions']:
            extensions = self.service.extensions()
            if extensions:
                if not raw:
                    print('Bugzilla extensions')
                    print('-------------------')
                    for e, v in extensions.iteritems():
                        print('{}: {}'.format(e, v['version']))
                else:
                    print(json.dumps(extensions))
            else:
                print('No installed Bugzilla extensions')

        if kw['users']:
            params = defaultdict(list)
            for user in kw['users']:
                if re.match(r'.+@.+', user):
                    params['names'].append(user)
                elif re.match(r'^\d+$', user):
                    params['ids'].append(user)
                else:
                    params['match'].append(user)
            users = self.service.users(params)
            if not raw:
                self.print_users(users)
            else:
                print(json.dumps(users))

        if kw['fields']:
            params = defaultdict(list)
            if not kw['fields'] == [None]:
                for field in kw['fields']:
                    if re.match(r'^\d+$', field):
                        params['ids'].append(field)
                    else:
                        params['names'].append(field)
            fields = self.service.fields(params)
            if not raw:
                print(json.dumps(fields, indent=2))
            else:
                print(json.dumps(fields))

        if kw['products']:
            params = defaultdict(list)
            for product in kw['products']:
               if re.match(r'^\d+$', product):
                   params['ids'].append(product)
               else:
                   params['names'].append(product)
            products = self.service.products(params)
            if not raw:
                self.print_products(products)
            else:
                print(json.dumps(products))

    def print_products(self, products):
        if products:
            for p in products:
                print('{:<12}: {}'.format('Name', p['name']))
                print('{:<12}: {}'.format('ID', p['id']))
                print('{:<12}: {}'.format('Milestone', p['default_milestone']))
                print('{:<12}: {}'.format('Class', p['classification']))
                print('{:<12}: {}'.format('Description', p['description']))
                print('{:<12}: {}'.format('Active', p['is_active']))
                print('-' * self.columns)
                print('Components')
                print('=' * self.columns)
                for c in p['components']:
                    print('  Name: {}'.format(c['name']))
                    print('  Description: {}'.format(c['description']))
                    print('  Default assigned: {}'.format(c['default_assigned_to']))
                    print('  Active: {}'.format(c['is_active']))
                    print('-' * self.columns)
                print('Versions')
                print('=' * self.columns)
                for v in p['versions']:
                    print('  Name: {}'.format(v['name']))
                    print('  ID: {}'.format(v['id']))
                    print('  Active: {}'.format(v['is_active']))
                    print('-' * self.columns)
                print('Milestones')
                print('=' * self.columns)
                for m in p['milestones']:
                    print('  Name: {}'.format(m['name']))
                    print('  ID: {}'.format(m['id']))
                    print('  Active: {}'.format(m['is_active']))
                    print('-' * self.columns)
        else:
            self.log('No matching products found')

    def print_users(self, users):
        if users:
            for u in users:
                if 'real_name' in u:
                    print('Real name: {}'.format(u['real_name']))
                print('Email: {}'.format(u['email']))
                if u['email'] != u['name']:
                    print('Login: {}'.format(u['name']))
                print('ID: {}'.format(u['id']))
                print('Can login: {}'.format(u['can_login']))
                if 'email_enabled' in u:
                    print('Email enabled: {}'.format(u['email_enabled']))
                print('-' * self.columns)
        else:
            self.log('No matching users found')

    def print_search(self, bugs, fields, output, **kw):
        if output is None:
            if fields == ['id', 'assigned_to', 'summary']:
                output = '{} {:<20} {}'
            else:
                output = ' '.join(['{}' for x in fields])

        count = 0
        for bug in bugs:
            if output == '-':
                for field in fields:
                    try:
                        value = getattr(bug, field)
                    except AttributeError:
                        raise CliError('"{}" is not a valid bug field'.format(field))
                    if value is None:
                        continue
                    if isinstance(value, list):
                        print('\n'.join(map(str, value)))
                    else:
                        print(value)
            else:
                try:
                    values = [getattr(bug, field) for field in fields]
                except AttributeError:
                    raise CliError('"{}" is not a valid bug field'.format(field))
                self._print_lines(output.format(*values), wrap=False)
            count += 1
        return count

    def _match_change(self, change, fields):
        change_aliases = {
            'attachment-description': 'attachments.description',
            'attachment-filename': 'attachments.filename',
            'attachment-mimetype': 'attachments.mimetype',
            'attachment-obsolete': 'attachments.isobsolete',
            'attachment-patch': 'attachments.ispatch',
            'blocks': 'blocked',
            'cc-accessible': 'cclist_accessible',
            'confirmed': 'everconfirmed',
            'depends': 'dependson',
            'flagname': 'flagtypes.name',
            'group': 'bug_group',
            'platform': 'rep_platform',
            'reporter-accessible': 'reporter_accessible',
            'severity': 'bug_severity',
            'title': 'short_desc',
            'url': 'bug_file_loc',
            'whiteboard': 'status_whiteboard',

            # Bugzilla < 4.4
            #'status': 'bug_status',
        }

        for field in fields:
            if ':' in field:
                key, value = field.split(':')
            else:
                key = field
                value = None

            try:
                key = change_aliases[key]
            except KeyError:
                pass

            if value is None or value == '':
                return change['field_name'] == key
            else:
                if value.startswith('+'):
                    return change['field_name'] == key and change['added'] == value[1:]
                elif value.startswith('-'):
                    return change['field_name'] == key and change['removed'] == value[1:]
                else:
                    return change['field_name'] == key and (
                        change['added'] == value or
                        change['removed'] == value
                    )

    def changes(self, ids, dry_run, creation_time, change_num, fields, output, creator, match, **kw):
        request = self.service.history(ids)

        self.log('Getting changes matching the following options:')
        self.log(request.options)

        if creator is not None and self.service.suffix is not None:
            creator = list(map(self.service._resuffix, creator))

        if dry_run: return
        history = request.send()

        for i in ids:
            changes = next(history)

            if creator is not None:
                changes = (x for x in changes if x.creator in creator)
            if creation_time is not None:
                changes = (x for x in changes if x.date >= parsetime(creation_time[1]).replace(tzinfo=utc))
            if match is not None:
                changes = (event for event in changes
                           for change in event.changes
                           if self._match_change(change=change, fields=match))
            if change_num is not None:
                if len(change_num) == 1 and change_num[0] < 0:
                    changes = list(changes)[change_num[0]:]
                else:
                    changes = (x for x in changes if x.count in change_num)

            if fields and output is None:
                output = ' '.join(['{}' for x in fields])

            if output == '-':
                for change in changes:
                    for field in fields:
                        try:
                            value = getattr(change, field)
                        except AttributeError:
                            raise CliError('"{}" is not a valid bug field'.format(field))
                        if value is None:
                            continue
                        if isinstance(value, list):
                            print('\n'.join(map(str, value)))
                        else:
                            print(value)
            elif fields and output:
                for change in changes:
                    try:
                        values = [getattr(change, field) for field in fields]
                    except AttributeError:
                        raise CliError('"{}" is not a valid bug field'.format(field))
                    self._print_lines(output.format(*values))
            else:
                changes = list(str(x) for x in changes)
                if changes:
                    print(self._header('=', 'Bug: {}'.format(str(i))))
                    self._print_lines(changes)

    def comments(self, ids, dry_run, creation_time, comment_num, fields, output, creator, attachment, **kw):
        request = self.service.comments(ids, created=creation_time)

        self.log('Getting comments matching the following options:')
        self.log(request.options)

        if creation_time is not None:
            creation_time = creation_time[1]

        if self.service.suffix is not None and creator is not None:
            creator = list(map(self.service._resuffix, creator))

        if dry_run: return
        comment_list = request.send()

        for i in ids:
            comments = next(comment_list)

            if creator is not None:
                comments = (x for x in comments if x.creator in creator)
            if attachment:
                comments = (x for x in comments if x.changes['attachment_id'] is not None)
            if comment_num is not None:
                if len(comment_num) == 1 and comment_num[0] < 0:
                    comments = list(comments)[comment_num[0]:]
                else:
                    comments = (x for x in comments if x.count in comment_num)

            if fields and output is None:
                output = ' '.join(['{}' for x in fields])

            if output == '-':
                for comment in comments:
                    for field in fields:
                        try:
                            value = getattr(comment, field)
                        except AttributeError:
                            raise CliError('"{}" is not a valid bug field'.format(field))
                        if value is None:
                            continue
                        if isinstance(value, list):
                            print('\n'.join(map(str, value)))
                        else:
                            print(value)
            elif fields and output:
                for comment in comments:
                    try:
                        values = [getattr(comment, field) for field in fields]
                    except AttributeError:
                        raise CliError('"{}" is not a valid bug field'.format(field))
                    self._print_lines(output.format(*values))
            else:
                comments = list(str(x) for x in comments)
                if comments:
                    print(self._header('=', 'Bug: {}'.format(str(i))))
                    self._print_lines(comments)

    #def history(self, ids, dry_run, creation_time, fields, creator, **kw):
    #    self.log('Getting all history matching the following options:')
    #    comment_list = self.service.comments(ids, created=creation_time)
    #    history = self.service.history(ids)

    #    for i in ids:
    #        comments = next(comment_list)
    #        changes = next(history)
    #        combined = sorted(chain(comments, changes), key=lambda event: event.date)

    def _print_item(self, bugs, get_comments, get_attachments, get_history, show_obsolete, **kw):
        for bug in bugs:
            print('=' * self.columns)
            for line in str(bug).splitlines():
                if len(line) <= self.columns:
                    print(line)
                else:
                    print(self.wrapper.fill(line))

            if bug.attachments:
                if show_obsolete:
                    attachments = [str(a) for a in bug.attachments]
                else:
                    attachments = [str(a) for a in bug.attachments if not a.is_obsolete]
                if attachments:
                    if str(bug):
                        print()
                    print('\n'.join(attachments))

            changes = []
            if get_history and get_comments:
                changes = sorted(chain(bug.history, bug.comments), key=lambda event: event.date)
            else:
                if get_history:
                    changes = bug.history
                elif get_comments:
                    changes = bug.comments
            if changes and (str(bug) or bug.attachments):
                print()
            self._print_lines((str(x) for x in changes))

    def change_fields(self, s):
        changes = s.split(',');
        fields = []
        for field in changes:
            try:
                key, value = field.split(':', 1)
                change = (key, value)
            except:
                change = (field, None)
            # TODO check key
            fields.append(change)
        return fields
