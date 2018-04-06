import os
import random
import re
import string
import subprocess
import sys
import tempfile
import textwrap

from . import __title__ as PROG
from .exceptions import BiteError


def raw_input_block():
    """Generator that yields multi-line input until EOF is detected."""
    while True:
        try:
            yield get_input()
        except EOFError:
            raise StopIteration


def launch_editor(initial_text, editor=None, comment_from='', prefix=PROG):
    """Use an editor for interactive text input."""
    if editor is None:
        editor = os.environ.get(f'{prefix.upper()}_EDITOR', os.environ.get('EDITOR', None))

    if editor:
        tmpfile = tempfile.NamedTemporaryFile(mode='w+', prefix=prefix, delete=False)
        with open(tmpfile.name, 'w') as f:
            f.write(comment_from)
            f.write(initial_text)

        try:
            subprocess.check_call([editor, tmpfile.name])
        except subprocess.CalledProcessError as e:
            raise BiteError(f'unable to launch editor {repr(editor)}: {e}')

        with open(tmpfile.name, 'r') as f:
            text = f.read()
        os.unlink(tmpfile.name)
        text = re.sub(f'(?m)^{prefix.upper()}:.*\n', '', text)
        return text
    return ''


def block_edit(comment, comment_from=''):
    prog = PROG.upper()
    comment = '\n'.join(f'{prog}: {line}' for line in comment.split('\n'))
    initial_text = textwrap.dedent(f"""\
        {prog}: ---------------------------------------------------
        {comment}
        {prog}: Any line beginning with '{prog}:' will be ignored.
        {prog}: ---------------------------------------------------
    """)

    editor = os.environ.get(f'{prog}_EDITOR', os.environ.get('EDITOR', None))
    if not editor:
        print(f'{comment}: (Press Ctrl+D to end)')
        return '\n'.join(raw_input_block())

    text = launch_editor(initial_text=initial_text, editor=editor, comment_from=comment_from)

    if text.strip():
        return text
    else:
        return ''


def get_input(prompt=''):
    if sys.stdout.isatty():
        return input(prompt)
    else:
        print(prompt, end='', file=sys.stderr)
        return input()


def confirm(prompt='Confirm', default=False):
    """Prompts for yes or no response from the user.

    Returns True for yes and False for no.

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
    if default:
        prompt = f'{prompt} (Y/n): '
    else:
        prompt = f'{prompt} (y/N): '

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


def str2bool(s):
    v = s.lower()
    if v in ("yes", "true", "1"):
        return True
    if v in ("no", "false", "0"):
        return False
    raise ValueError(f'invalid boolean value {repr(s)}')
