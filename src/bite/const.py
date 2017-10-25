import os
import sys

from snakeoil import mappings

from . import __title__

_reporoot = os.path.realpath(__file__).rsplit(os.path.sep, 3)[0]
_module = sys.modules[__name__]
try:
    # This is a file written during installation;
    # if it exists, we defer to it. If it doesn't, then we're
    # running from a git checkout or a tarball.
    from . import _const as _defaults
    CONFIG_PATH = None
except ImportError:
    _defaults = object()
    CONFIG_PATH = os.path.join(_reporoot, 'config')


def _GET_CONST(attr, default_value):
    consts = mappings.ProxiedAttrs(_module)
    is_tuple = not isinstance(default_value, str)
    if is_tuple:
        default_value = tuple(x % consts for x in default_value)
    else:
        default_value %= consts

    result = getattr(_defaults, attr, default_value)
    if is_tuple:
        result = tuple(result)
    return result


# determine XDG compatible paths
for xdg_var, var_name, fallback_dir in (
        ('XDG_CONFIG_HOME', 'USER_CONFIG_PATH', '~/.config'),
        ('XDG_CACHE_HOME', 'USER_CACHE_PATH', '~/.cache'),
        ('XDG_DATA_HOME', 'USER_DATA_PATH', '~/.local/share')):
    setattr(_module, var_name,
            os.environ.get(xdg_var, os.path.join(os.path.expanduser(fallback_dir), __title__)))

DATA_PATH = _GET_CONST('DATA_PATH', _reporoot)
if CONFIG_PATH is None:
    CONFIG_PATH = _GET_CONST('CONFIG_PATH', '%(DATA_PATH)s/config')
