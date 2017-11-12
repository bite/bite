import base64
from collections import OrderedDict
import os
import re
import stat
import subprocess
import sys
from itertools import chain, groupby

from dateutil.parser import parse as parsetime
from snakeoil.strings import pluralism

from .. import Cli
from ... import const
from ...utils import block_edit, confirm, get_input
from ...exceptions import CliError
from ...utc import utc

class Bugzilla(Cli):
    """CLI for Bugzilla service."""

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
                # assume default product has the lowest ID
                default_product = self.service.cache['products'][0]
                line = get_input('Enter version (default: {}): '.format(default_product))
                if len(line):
                    kw['version'] = line
                else:
                    kw['version'] = default_product
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
        options_log.append('=' * const.COLUMNS)
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
        options_log.append('=' * const.COLUMNS)

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

    def version(self, dry_run=False):
        version = self.service.version()
        print('Bugzilla version: {}'.format(version))

    def extensions(self, dry_run=False):
        extensions = self.service.extensions()
        if extensions:
            print('Bugzilla extensions')
            print('-------------------')
            for e, v in extensions.items():
                print('{}: {}'.format(e, v['version']))
        else:
            print('No installed Bugzilla extensions')

    def users(self, users, dry_run=False):
        params = {}
        for user in users:
            if re.match(r'.+@.+', user):
                params.setdefault('names', []).append(user)
            elif re.match(r'^\d+$', user):
                params.setdefault('ids', []).append(user)
            else:
                params.setdefault('match', []).append(user)

        request = self.service.UsersRequest(**params)

        self.log('Getting users matching the following options:')
        self.log_t(request.options, prefix='   - ')

        if dry_run: return
        data = self.service.send(request)
        self.print_users(data)

    def fields(self, fields=None, dry_run=False):
        params = {}
        if fields is not None:
            for field in fields:
                if re.match(r'^\d+$', field):
                    params.setdefault('ids', []).append(field)
                else:
                    params.setdefault('names', []).append(field)

        request = self.service.FieldsRequest(**params)

        self.log('Getting fields matching the following options:')
        self.log_t(request.options, prefix='   - ')

        if dry_run: return
        data = self.service.send(request)

        for field in data:
            print('{} ({})'.format(field['display_name'], field['name']))
            if self.verbose or fields and len(fields) == 1:
                for value in field.get('values', []):
                    if value.get('name', False):
                        print('  {}'.format(value['name']))
                        if 'is_open' in value:
                            print('    open: {}'.format(value['is_open']))

    def products(self, products, dry_run=False):
        params = {}
        if products is not None:
            for product in products:
                if re.match(r'^\d+$', product):
                    params.setdefault('ids', []).append(product)
                else:
                    params.setdefault('names', []).append(product)

        request = self.service.ProductsRequest(**params)

        self.log('Getting products matching the following options:')
        self.log_t(request.options, prefix='   - ')

        if dry_run: return
        data = self.service.send(request)

        self.print_products(data)

    def print_products(self, products):
        if products:
            for p in products:
                print('{:<12}: {}'.format('Name', p['name']))
                print('{:<12}: {}'.format('ID', p['id']))
                print('{:<12}: {}'.format('Milestone', p['default_milestone']))
                print('{:<12}: {}'.format('Class', p['classification']))
                print('{:<12}: {}'.format('Description', p['description']))
                print('{:<12}: {}'.format('Active', p['is_active']))
                print('-' * const.COLUMNS)
                print('Components')
                print('=' * const.COLUMNS)
                for c in p['components']:
                    print('  Name: {}'.format(c['name']))
                    print('  Description: {}'.format(c['description']))
                    print('  Default assigned: {}'.format(c['default_assigned_to']))
                    print('  Active: {}'.format(c['is_active']))
                    print('-' * const.COLUMNS)
                print('Versions')
                print('=' * const.COLUMNS)
                for v in p['versions']:
                    print('  Name: {}'.format(v['name']))
                    print('  ID: {}'.format(v['id']))
                    print('  Active: {}'.format(v['is_active']))
                    print('-' * const.COLUMNS)
                print('Milestones')
                print('=' * const.COLUMNS)
                for m in p['milestones']:
                    print('  Name: {}'.format(m['name']))
                    print('  ID: {}'.format(m['id']))
                    print('  Active: {}'.format(m['is_active']))
                    print('-' * const.COLUMNS)
        else:
            self.log('No matching products found')

    def print_users(self, users):
        print_fields = OrderedDict((
            ('real_name', 'Real name'),
            ('email', 'Email'),
            ('id', 'ID'),
            ('can_login', 'Can login'),
            ('email_enabled', 'Email enabled'),
        ))

        if users:
            for u in users:
                for k, v in print_fields.items():
                    if k in u:
                        print('{}: {}'.format(v, u[k]))
                print('-' * const.COLUMNS)
        else:
            self.log('No matching users found')

    def print_search(self, bugs, fields, output=None, **kw):
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
                        raise CliError('{!r} is not a valid field'.format(field))
                    if value is None:
                        continue
                    if isinstance(value, list):
                        print('\n'.join(map(str, value)))
                    else:
                        print(value)
            else:
                try:
                    values = []
                    for field in fields:
                        values.append(getattr(bug, field))
                except AttributeError:
                    raise CliError('{!r} is not a valid field'.format(field))
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

    def changes(self, ids, dry_run=False, creation_time=None, change_num=None, fields=None, output=None, creator=None,
                match=None):
        request = self.service.HistoryRequest(ids, created=creation_time)

        self.log('Getting changes matching the following options:')
        self.log_t(request.options, prefix='   - ')

        if creator is not None and self.service.suffix is not None:
            creator = list(map(self.service._resuffix, creator))

        if dry_run: return
        history = self.service.send(request)

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
                            raise CliError('{!r} is not a valid bug field'.format(field))
                        if value is None:
                            continue
                        if isinstance(value, list):
                            print('\n'.join(map(str, value)))
                        else:
                            print(value)
            elif fields and output:
                for change in changes:
                    try:
                        values = []
                        for field in fields:
                            values.append(getattr(change, field))
                    except AttributeError:
                        raise CliError('{!r} is not a valid field'.format(field))
                    self._print_lines(output.format(*values))
            else:
                changes = list(str(x) for x in changes)
                if changes:
                    print(self._header('=', 'Bug: {}'.format(str(i))))
                    self._print_lines(changes)

    def comments(self, ids, dry_run=False, creation_time=None, comment_num=None, fields=None, output=None, creator=None,
                 attachment=False):
        request = self.service.CommentsRequest(ids, created=creation_time)

        if creator is not None:
            request.options.append('Creator{}: {}'.format(pluralism(creator), ', '.join(creator)))
        if attachment:
            request.options.append('Attachments: yes')
        if comment_num is not None:
            request.options.append('Comment number{}: {}'.format(pluralism(comment_num), ', '.join(map(str, comment_num))))

        self.log('Getting comments matching the following options:')
        self.log_t(request.options, prefix='   - ')

        if creation_time is not None:
            creation_time = creation_time[1]

        if self.service.suffix is not None and creator is not None:
            creator = list(map(self.service._resuffix, creator))

        if dry_run: return
        comment_list = self.service.send(request)

        for i in ids:
            comments = next(comment_list)

            if creator is not None:
                comments = (x for x in comments if x.creator in creator)
            if attachment:
                comments = (x for x in comments if x.changes['attachment_id'] is not None)
            if comment_num is not None:
                if any(x < 0 for x in comment_num):
                    comments = list(comments)
                    selected = []
                    for x in comment_num:
                        try:
                            selected.append(comments[x])
                        except IndexError:
                            pass
                    comments = selected
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
                            raise CliError('{!r} is not a valid bug field'.format(field))
                        if value is None:
                            continue
                        if isinstance(value, list):
                            print('\n'.join(map(str, value)))
                        else:
                            print(value)
            elif fields and output:
                for comment in comments:
                    try:
                        values = []
                        for field in fields:
                            values.append(getattr(comment, field))
                    except AttributeError:
                        raise CliError('{!r} is not a valid field'.format(field))
                    self._print_lines(output.format(*values))
            else:
                comments = list(str(x) for x in comments)
                if comments:
                    print(self._header('=', 'Bug: {}'.format(str(i))))
                    self._print_lines(comments)

    def _print_item(self, bugs, get_comments=False, get_history=False, show_obsolete=False, **kw):
        for bug in bugs:
            print('=' * const.COLUMNS)
            for line in str(bug).splitlines():
                if len(line) <= const.COLUMNS:
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
