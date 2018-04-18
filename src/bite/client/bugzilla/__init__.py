from collections import OrderedDict
from itertools import chain
import re
import subprocess
import sys

from snakeoil.demandload import demandload
from snakeoil.strings import pluralism

from .. import Cli, login_required
from ...exceptions import BiteError
from ...utils import block_edit, get_input

demandload('bite:const')


class Bugzilla(Cli):
    """CLI for Bugzilla service."""

    def attach(self, *args, **kw):
        if kw['comment'] is None:
            kw['comment'] = block_edit('Enter optional long description of attachment')
        super().attach(*args, **kw)

    def create(self, *args, **kw):
        # load description from file or stdin
        if kw['description_from']:
            try:
                if kw['description_from'] == '-':
                    kw['description'] = sys.stdin.read()
                else:
                    kw['description'] = open(kw['description_from'], 'r').read()
            except IOError as e:
                raise BiteError(f"Unable to read file: {kw['description_from']}: {e}")

        if kw.get('batch', False):
            self.log('Press Ctrl+C at any time to abort.')

            if not kw['product']:
                while not kw['product'] or len(kw['product']) < 1:
                    kw['product'] = get_input('Enter product: ')
            else:
                self.log(f"Enter product: {kw['product']}")

            if not kw['component']:
                while not kw['component'] or len(kw['component']) < 1:
                    kw['component'] = get_input('Enter component: ')
            else:
                self.log(f"Enter component: {kw['component']}")

            if not kw['version']:
                # assume default product has the lowest ID
                default_product = self.service.cache['products'][0]
                line = get_input(f"Enter version (default: {default_product})")
                if len(line):
                    kw['version'] = line
                else:
                    kw['version'] = default_product
            else:
                self.log(f"Enter version: {kw['version']}")

            if not kw['summary']:
                while not kw['summary'] or len(kw['summary']) < 1:
                    kw['summary'] = get_input('Enter title: ')
            else:
                self.log(f"Enter title: {kw['summary']}")

            if not kw['description']:
                line = block_edit('Enter bug description: ')
                if len(line):
                    kw['description'] = line
            else:
                self.log(f"Enter bug description: {kw['description']}")

            if not kw['op_sys']:
                op_sys_msg = 'Enter operating system where this bug occurs: '
                line = get_input(op_sys_msg)
                if len(line):
                    kw['op_sys'] = line
            else:
                self.log(f"Enter operating system: {kw['op_sys']}")

            if not kw['platform']:
                platform_msg = 'Enter hardware platform where this bug occurs: '
                line = get_input(platform_msg)
                if len(line):
                    kw['platform'] = line
            else:
                self.log(f"Enter hardware platform: {kw['platform']}")

            if kw['priority'] is None:
                priority_msg = 'Enter priority (e.g. normal) (optional): '
                line = get_input(priority_msg)
                if len(line):
                    kw['priority'] = line
            else:
                self.log(f"Enter priority (optional): {kw['priority']}")

            if kw['severity'] is None:
                severity_msg = 'Enter severity (e.g. normal) (optional): '
                line = get_input(severity_msg)
                if len(line):
                    kw['severity'] = line
            else:
                self.log(f"Enter severity (optional): {kw['severity']}")

            if kw['target_milestone'] is None:
                milestone_msg = 'Enter target milestone (optional): '
                line = get_input(milestone_msg)
                if len(line):
                    kw['target_milestone'] = line
            else:
                self.log(f"Enter target milestone (optional): {kw['target_milestone']}")

            if kw['alias'] is None:
                alias_msg = 'Enter alias (optional): '
                line = get_input(alias_msg)
                if len(line):
                    kw['alias'] = line
            else:
                self.log(f"Enter alias (optional): {kw['alias']}")

            if kw['assigned_to'] is None:
                assign_msg = 'Enter assignee (e.g. dev@email.com) (optional): '
                line = get_input(assign_msg)
                if len(line):
                    kw['assigned_to'] = line
            else:
                self.log(f"Enter assignee (optional): {kw['assigned_to']}")

            if kw['status'] is None:
                status_msg = 'Enter status (optional): '
                line = get_input(status_msg)
                if len(line):
                    kw['status'] = line
            else:
                self.log(f"Enter status (optional): {kw['status']}")

            if kw['cc'] is None:
                cc_msg = 'Enter CCs (comma separated) (optional): '
                line = get_input(cc_msg)
                if len(line):
                    kw['cc'] = line.split(',')
            else:
                self.log(f"Enter CCs (optional): {kw['cc']}")

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
                self.log(f"Enter groups (optional): {kw['groups']}")

            if kw['append_command'] is None:
                kw['append_command'] = get_input('Append the output of the following command (leave blank for none): ')
            else:
                self.log(f"Append command (optional): {kw['append_command']}")

        # append the output from append_command to the description
        if kw['append_command'] is not None and kw['append_command'] != '':
            append_command_output = subprocess.check_output(kw['append_command'])
            kw['description'] = kw['description'] + '\n\n' + '$ ' + kw['append_command'] + '\n' + append_command_output

        options_log = [
            '=' * const.COLUMNS,
            f"Product: {kw['product']}",
            f"Component: {kw['component']}",
            f"Version: {kw['version']}",
            f"Title: {kw['summary']}",
            f"OS: {kw['op_sys']}",
            f"Platform: {kw['platform']}",
            f"Priority: {kw['priority']}",
            f"Severity: {kw['severity']}",
        ]
        if kw['target_milestone'] is not None:
            options_log.append(f"Milestone: {kw['target_milestone']}")
        if kw['alias'] is not None:
            options_log.append(f"Alias: {kw['alias']}")
        if kw['assigned_to'] is not None:
            options_log.append(f"Assigned to: {self.service._desuffix(kw['assigned_to'])}")
            # add potentially missing domain suffix
            kw['assigned_to'] = self.service._resuffix(kw['assigned_to'])
        if kw['status'] is not None:
            options_log.append(f"Status: {kw['status']}")
        if kw['cc'] is not None:
            options_log.append(f"CC: {', '.join(map(self.service._desuffix, kw['cc']))}")
            # add potentially missing domain suffixes
            kw['cc'] = list(map(self.service._resuffix, kw['cc']))
        #if kw['keywords'] is not None:
        #    options_log.append('{:<12}: {}'.format('Keywords', ', '.join(kw['keywords'])))
        if kw['groups'] is not None:
            options_log.append(f"Groups: {', '.join(kw['groups'])}")
        options_log.append(self._header('-', 'Description'))
        if kw['description'] is not None:
            # interpret backslash escapes
            kw['description'] = kw['description'].decode('string_escape')
            options_log.append(kw['description'])
        options_log.append('=' * const.COLUMNS)
        kw['options_log'] = options_log

        super().create(*args, **kw)

    def modify(self, *args, **kw):
        comment_from = kw.get('comment_from')
        if comment_from is not None:
            try:
                if comment_from == '-':
                    kw['comment-body'] = sys.stdin.read()
                else:
                    kw['comment-body'] = open(comment_from, 'r').read()
            except IOError as e:
                raise BiteError('Unable to read file: {comment_from}: {e}')

        if kw.get('comment_editor'):
            kw['comment-body'] = block_edit('Enter comment:').rstrip()

        super().modify(*args, **kw)

    def _render_changes(self, bug, **kw):
        yield self._header('=', f"Bug: {str(bug['id'])}")
        changes = bug['changes']

        if len(changes):
            yield self._header('-', 'Modified fields')
            for k, v in changes.items():
                try:
                    field = self.service.item.attributes[k]
                except KeyError:
                    field = k

                if v['removed'] and v['added']:
                    yield f"{field}: {v['removed']} -> {v['added']}"
                else:
                    if v['removed']:
                        yield f"{field}: -{v['removed']}"
                    elif v['added']:
                        yield f"{field}: +{v['added']}"
        else:
            if 'comment-body' not in kw:
                yield 'No changes made'

        if kw.get('comment-body', None) is not None:
            yield self._header('-', 'Added comment')
            yield kw['comment-body']

    def version(self, dry_run=False):
        version = self.service.version()
        print(f'Bugzilla version: {version}')

    def extensions(self, dry_run=False):
        extensions = self.service.extensions()
        if extensions:
            print('Bugzilla extensions')
            print('-------------------')
            for ext, v in extensions.items():
                print(f"{ext}: {v['version']}")
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
            print(f"{field['display_name']} ({field['name']})")
            if self.verbose or fields and len(fields) == 1:
                for value in field.get('values', []):
                    if value.get('name', False):
                        print(f"  {value['name']}")
                        if 'is_open' in value:
                            print(f"    open: {value['is_open']}")

    def products(self, products=None, dry_run=False):
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
                        print(f'{v}: {u[k]}')
                print('-' * const.COLUMNS)
        else:
            self.log('No matching users found')

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

    def changes(self, ids, dry_run=False, **kw):
        request = self.service.HistoryRequest(ids, created=kw.get('creation_time', None))

        self.log('Getting changes matching the following options:')
        self.log_t(request.options, prefix='   - ')

        if kw.get('creator', None) is not None and self.service.suffix is not None:
            kw['creator'] = list(map(self.service._resuffix, kw['creator']))

        if dry_run: return
        history_iter = request.send()
        lines = chain.from_iterable(self._render_history(ids[i], history, **kw)
                                    for i, history in enumerate(history_iter))
        print(*lines, sep='\n')

    def _render_history(self, bug_id, changes, creation_time=None, change_num=None,
                        fields=None, output=None, creator=None, match=None):
        if creator is not None:
            changes = (x for x in changes if x.creator in creator)
        if creation_time is not None:
            changes = (x for x in changes if x.date >= creation_time)
        if match is not None:
            changes = (
                event for event in changes
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
                        raise BiteError(f'invalid field: {field!r}')
                    if value is None:
                        continue
                    if isinstance(value, list):
                        yield from map(str(value))
                    else:
                        yield value
        elif fields and output:
            for change in changes:
                values = (getattr(change, field, None) for field in fields)
                yield from self._iter_lines(output.format(*values))
        else:
            changes = list(str(x) for x in changes)
            if changes:
                yield self._header('=', f'Bug: {bug_id}')
                yield from self._iter_lines(changes)

    def comments(self, ids, dry_run=False, **kw):
        creation_time = kw.get('creation_time', None)
        creator = kw.get('creator', None)
        attachment = kw.get('attachment', False)
        comment_num = kw.get('comment_num', None)

        request = self.service.CommentsRequest(ids, created=creation_time)

        if creator is not None:
            request.options.append(f"Creator{pluralism(creator)}: {', '.join(creator)}")
        if attachment:
            request.options.append('Attachments: yes')
        if comment_num is not None:
            request.options.append(
                f"Comment number{pluralism(comment_num)}: {', '.join(map(str, comment_num))}")

        self.log('Getting comments matching the following options:')
        self.log_t(request.options, prefix='   - ')

        if self.service.suffix is not None and creator is not None:
            creator = list(map(self.service._resuffix, creator))

        if dry_run: return
        comments_iter = request.send()
        lines = chain.from_iterable(self._render_comments(ids[i], comments, **kw)
                                    for i, comments in enumerate(comments_iter))
        print(*lines, sep='\n')

    def _render_comments(self, bug_id, comments, creation_time=None, comment_num=None,
                        fields=None, output=None, creator=None, attachment=False):
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
                        raise BiteError(f'invalid field: {field!r}')
                    if value is None:
                        continue
                    if isinstance(value, list):
                        yield from map(str, value)
                    else:
                        yield value
        elif fields and output:
            for comment in comments:
                values = (getattr(comment, field, None) for field in fields)
                yield from self._iter_lines(output.format(*values))
        else:
            comments = list(str(x) for x in comments)
            if comments:
                yield self._header('=', f'Bug: {bug_id}')
                yield from self._iter_lines(comments)

    def _render_item(self, bug, show_obsolete=False, **kw):
        yield '=' * const.COLUMNS
        for line in str(bug).splitlines():
            if len(line) <= const.COLUMNS:
                yield line
            else:
                yield self.wrapper.fill(line)

        if bug.attachments:
            if show_obsolete:
                attachments = [str(a) for a in bug.attachments]
            else:
                attachments = [str(a) for a in bug.attachments if not a.is_obsolete]
            if attachments:
                if str(bug):
                    yield ''
                yield from attachments

        if bug.events and (str(bug) or bug.attachments):
            yield ''
        yield from self._iter_lines(str(x) for x in bug.events)

    def change_fields(self, s):
        changes = s.split(',')
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


class Bugzilla5_0(Bugzilla):
    """CLI for Bugzilla 5.0 service."""

    def apikeys(self, generate=None, revoke=None, *args, **kw):
        if generate is not None:
            # TODO: cache generated key for use with bite if it's named 'bite'
            self.service.apikeys.generate(generate)
        elif revoke is not None:
            unrevoke, revoke = revoke
            self.service.apikeys.revoke(disable=revoke, enable=unrevoke)
        else:
            # fallback to listing available apikeys
            keys = [x for x in self.service.apikeys]
            if self.verbose and keys:
                print('{:<41} {:<16} {:<26} {:<8}'.format(
                    'API key', 'Description', 'Last used', 'Revoked'))
                print('-' * const.COLUMNS)
                for k in keys:
                    print(f'{k.key:<41} {k.desc[:15]:<16} {str(k.used):<26} {k.revoked}')
            else:
                for k in (x for x in keys if not x.revoked):
                    print(f'{k.key} {k.desc}')
