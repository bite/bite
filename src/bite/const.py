import os
import sys

from snakeoil import mappings

from bite import __title__

_reporoot = os.path.realpath(__file__).rsplit(os.path.sep, 3)[0]
try:
    # This is a file written during installation;
    # if it exists, we defer to it. If it doesn't, then we're
    # running from a git checkout or a tarball.
    from bite import _const as _defaults
    CONFIG_PATH = None
except ImportError:
    _defaults = object()
    CONFIG_PATH = os.path.join(_reporoot, 'config')


def _GET_CONST(attr, default_value):
    consts = mappings.ProxiedAttrs(sys.modules[__name__])
    is_tuple = not isinstance(default_value, str)
    if is_tuple:
        default_value = tuple(x % consts for x in default_value)
    else:
        default_value %= consts

    result = getattr(_defaults, attr, default_value)
    if is_tuple:
        result = tuple(result)
    return result


if 'XDG_CONFIG_HOME' in os.environ:
    USER_CONFIG_PATH = os.path.join(os.environ['XDG_CONFIG_HOME'], __title__)
else:
    USER_CONFIG_PATH = os.path.expanduser(os.path.join('~/.config', __title__))

if 'XDG_CACHE_HOME' in os.environ:
    USER_CACHE_PATH = os.path.join(os.environ['XDG_CACHE_HOME'], __title__)
else:
    USER_CACHE_PATH = os.path.expanduser(os.path.join('~/.cache', __title__))

if 'XDG_DATA_HOME' in os.environ:
    USER_DATA_PATH = os.path.join(os.environ['XDG_DATA_HOME'], __title__)
else:
    USER_DATA_PATH = os.path.expanduser(os.path.join('~/.local/share', __title__))

DATA_PATH = _GET_CONST('DATA_PATH', _reporoot)
if CONFIG_PATH is None:
    CONFIG_PATH = _GET_CONST('CONFIG_PATH', '%(DATA_PATH)s/config')
