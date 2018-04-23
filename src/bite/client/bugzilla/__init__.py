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
        # TODO: check if cache exists, if it doesn't pull a copy
        # load description from file or stdin
        description_from = kw.get('description_from')
        if description_from:
            try:
                if description_from == '-':
                    kw['description'] = sys.stdin.read()
                else:
                    with open(description_from, 'r') as f:
                        kw['description'] = f.read()
            except IOError as e:
                raise BiteError(f"Unable to read file: {description_from}: {e}")

        if not kw.get('batch'):
            self.log('Press Ctrl+C at any time to abort.')

            while not kw.get('summary') or not kw['summary']:
                kw['summary'] = get_input('Title: ')

            if not kw.get('description'):
                data = block_edit('Bug description: ').strip()
                if data:
                    kw['description'] = data

            while not kw.get('product') or not kw['product']:
                kw['product'] = get_input('Product: ')

            while not kw.get('component') or not kw['component']:
                kw['component'] = get_input('Component: ')

            if not kw.get('version'):
                cached_versions = self.service.cache.get('versions')
                default_str = ''
                if cached_versions:
                    # assume default version has the lowest ID
                    default_version = cached_versions[0]
                    default_str = f' (default: {default_version})'
                version = get_input(f"Version{default_str}: ")
                if version:
                    kw['version'] = version
                else:
                    kw['version'] = default_version

            if not kw.get('op_sys'):
                data = get_input('OS: ')
                if data:
                    kw['op_sys'] = data

            if not kw.get('platform'):
                data = get_input('Hardware: ')
                if data:
                    kw['platform'] = data

            if not kw.get('priority'):
                data = get_input('Priority (optional): ')
                if data:
                    kw['priority'] = data

            if not kw.get('severity'):
                data = get_input('Severity (optional): ')
                if data:
                    kw['severity'] = data

            if not kw.get('target_milestone'):
                data = get_input('Target milestone (optional): ')
                if data:
                    kw['target_milestone'] = data

            if not kw.get('alias'):
                data = get_input('Alias (optional): ')
                if data:
                    kw['alias'] = data

            if not kw.get('assigned_to'):
                data = get_input('Assignee (e.g. dev@email.com) (optional): ')
                if data:
                    kw['assigned_to'] = data

            if not kw.get('status'):
                data = get_input('Status (optional): ')
                if data:
                    kw['status'] = data

            if not kw.get('cc'):
                data = get_input('CCs (comma separated) (optional): ')
                if data:
                    kw['cc'] = data.split(',')

            if not kw.get('groups'):
                data = get_input('Groups (comma separated) (optional): ')
                if data:
                    kw['groups'] = data.split(',')

        # append the output from append_command to the description
        append_command = kw.get('append_command')
        if append_command:
            try:
                append_command_output = subprocess.check_output(append_command).strip()
                kw['description'] = kw['description'] + '\n\n' + '$ ' + append_command + '\n' + append_command_output
            except (subprocess.CalledProcessError, FileNotFoundError) as e:
                self.log(f'Command failed: {str(e)}')

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

    def version(self, **kw):
        version = self.service.version()
        print(f'Bugzilla version: {version}')

    def extensions(self, **kw):
        extensions = self.service.extensions()
        if extensions:
            print('Bugzilla extensions')
            print('-------------------')
            for ext, v in extensions.items():
                print(f"{ext}: {v['version']}")
        else:
            print('No installed Bugzilla extensions')

    def users(self, users, dry_run=False, **kw):
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

    def fields(self, fields=None, dry_run=False, **kw):
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

    def products(self, products=None, dry_run=False, **kw):
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
                        fields=None, output=None, creator=None, match=None, **kw):
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
                        fields=None, output=None, creator=None, attachment=False, **kw):
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

    def savedsearches(self, save=None, remove=None, *args, **kw):
        if save is not None:
            name, url = save
            self.service.saved_searches.save(name, url)
        elif remove is not None:
            self.service.saved_searches.remove(remove)
        else:
            # fallback to listing available saved searches
            for k in self.service.saved_searches.keys():
                print(k)
