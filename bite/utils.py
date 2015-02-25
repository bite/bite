import codecs
import os
import random
import re
import sys
import string
import tempfile

from bite.exceptions import CommandError

COMMENT_TEMPLATE = \
"""
BITE: ---------------------------------------------------
{}
BITE: Any line beginning with 'BITE:' will be ignored.
BITE: ---------------------------------------------------
"""

def raw_input_block():
    """ Allows multiple line input until a Ctrl+D is detected.

    @rtype: string
    """
    target = ''
    while True:
        try:
            line = get_input()
            target += line + '\n'
        except EOFError:
            return target

def terminal_width():
    """Return estimated terminal width."""
    if sys.platform == 'win32':
        return win32utils.get_console_size()[0]
    width = 0
    try:
        width = int(os.environ['COLUMNS'])
    except KeyError:
        try:
            import struct, fcntl, termios
            s = struct.pack(str('HHHH'), 0, 0, 0, 0)
            x = fcntl.ioctl(1, termios.TIOCGWINSZ, s)
            width = struct.unpack(str('HHHH'), x)[1]
        except IOError:
            pass
    if width <= 0:
        width = 80

    return width

def launch_editor(initial_text, comment_from='', comment_prefix='BITE:'):
    """Launch an editor with some default text.

    @rtype: string
    """
    (fd, name) = tempfile.mkstemp('bite')
    f = os.fdopen(fd, 'w')
    f.write(comment_from)
    f.write(initial_text)
    f.close()

    editor = (os.environ.get('BITE_EDITOR') or
              os.environ.get('EDITOR'))
    if editor:
        result = os.system('{} "{}"'.format(editor, name))
        if result != 0:
            raise CommandError('Unable to launch editor: {}'.format(editor))

        new_text = codecs.open(name, encoding='utf-8').read()
        new_text = re.sub('(?m)^{}.*\n'.format(comment_prefix), '', new_text)
        os.unlink(name)
        return new_text

    return ''

def block_edit(comment, comment_from=''):
    editor = (os.environ.get('BITE_EDITOR') or
              os.environ.get('EDITOR'))

    if not editor:
        print('{}: {}'.format(comment, ': (Press Ctrl+D to end)'))
        new_text = raw_input_block()
        return new_text

    initial_text = '\n'.join(['BITE: {}'.format(line) for line in comment.split('\n')])
    new_text = launch_editor(COMMENT_TEMPLATE.format(initial_text), comment_from)

    if new_text.strip():
        return new_text
    else:
        return ''

def get_input(prompt=''):
    encoding = sys.stdin.encoding
    if encoding is None:
        encoding = 'utf-8'
        sys.stdin = open('/dev/tty')

    if sys.stdout.isatty():
        return raw_input(prompt).decode(encoding)
    else:
        print(prompt, end='', file=sys.stderr)
        return raw_input().decode(encoding)

def confirm(prompt=None, default=False):
    """
    Prompts for yes or no response from the user. Returns True for yes and
    False for no.

    'default' should be set to the default value assumed by the caller when
    user simply types ENTER.

    >>> confirm(prompt='Create Directory?', default=True)
    Create Directory? (Y/n):
    True
    >>> confirm(prompt='Create Directory?', default=False)
    Create Directory? (y/N):
    False
    >>> confirm(prompt='Create Directory?', default=False)
    Create Directory? (y/N): y
    True
    """

    if prompt is None:
        prompt = 'Confirm'

    if default:
        prompt = '{} ({}/{}): '.format(prompt, 'Y', 'n')
    else:
        prompt = '{} ({}/{}): '.format(prompt, 'y', 'N')

    while True:
        ans = get_input(prompt)
        if not ans:
            return default
        if ans not in ['y', 'Y', 'n', 'N']:
            print('please enter y or n.')
            continue
        if ans == 'y' or ans == 'Y':
            return True
        if ans == 'n' or ans == 'N':
            return False

def id_generator(size=16, chars=string.ascii_uppercase + string.digits):
    return ''.join(random.choice(chars) for x in range(size))

def strikethrough(s):
    return ''.join([(char + r'\u0336') for char in s])
