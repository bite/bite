import os
import random
import re
import string
import subprocess
import sys
import tempfile

from snakeoil.demandload import demandload
from snakeoil.sequences import iflatten_instance

from . import __title__ as prog
from .exceptions import BiteError

demandload('bite:const')

PROG = prog.upper()


def raw_input_block():
    """Generator that yields multi-line input until EOF is detected."""
    while True:
        try:
            yield get_input()
        except EOFError:
            raise StopIteration


def launch_browser(urls, browser=const.BROWSER):
    """Launch URLs in a browser."""
    urls = list(iflatten_instance(urls))
    try:
        subprocess.Popen(
            [browser] + urls,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except (PermissionError, FileNotFoundError) as e:
        raise BiteError(f'failed running browser: {browser}: {e.strerror}')


def launch_editor(initial_text, editor=None, comment_from='', tool=PROG):
    """Use an editor for interactive text input."""
    if editor is None:
        editor = os.environ.get(f'{tool}_EDITOR', os.environ.get('EDITOR', None))

    if editor:
        tmpfile = tempfile.NamedTemporaryFile(mode='w+', prefix=prog, delete=False)
        with open(tmpfile.name, 'w') as f:
            f.write(comment_from)
            f.write(initial_text)

        try:
            subprocess.check_call([editor, tmpfile.name])
        except subprocess.CalledProcessError as e:
            raise BiteError(f'unable to launch editor {editor!r}: {e}')

        with open(tmpfile.name, 'r') as f:
            text = f.read()
        os.unlink(tmpfile.name)
        text = re.sub(f'(?m)^{tool}:.*\n', '', text)
        return text
    return ''


def block_edit(comment, comment_from=''):
    comment = '\n'.join(f'{PROG}: {line}' for line in comment.split('\n'))
    initial_text = f"""\

{PROG}: ---------------------------------------------------
{comment}
{PROG}: Any line beginning with '{PROG}:' will be ignored.
{PROG}: ---------------------------------------------------
"""

    editor = os.environ.get(f'{PROG}_EDITOR', os.environ.get('EDITOR', None))
    if not editor:
        print(f'{comment}: (Press Ctrl+D to end)')
        return '\n'.join(raw_input_block())

    text = launch_editor(initial_text=initial_text, editor=editor, comment_from=comment_from)

    if text.strip():
        return text
    else:
        return ''


def get_input(prompt='', strip=True):
    if sys.stdout.isatty():
        data = input(prompt)
    else:
        print(prompt, end='', file=sys.stderr)
        data = input()

    if strip:
        data = data.strip()
    return data


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
    raise ValueError(f'invalid boolean value: {s!r}')


def dict2tuples(dct):
    for k, v in dct.items():
        if isinstance(v, (list, tuple)):
            yield from ((k, x) for x in v)
        else:
            yield (k, v)
