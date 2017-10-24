import os
import sys

from snakeoil import mappings

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
    USER_CONFIG_PATH = os.path.join(os.environ['XDG_CONFIG_HOME'], 'bite')
else:
    USER_CONFIG_PATH = os.path.expanduser('~/.config/bite/')

DATA_PATH = _GET_CONST('DATA_PATH', _reporoot)
if CONFIG_PATH is None:
    if os.path.exists(USER_CONFIG_PATH):
        CONFIG_PATH = USER_CONFIG_PATH
    else:
        # fall back to installed example config
        CONFIG_PATH = _GET_CONST('CONFIG_PATH', '%(DATA_PATH)s/config')
