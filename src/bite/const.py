from functools import partial
from importlib import import_module
import os
from shutil import get_terminal_size
import sys

from snakeoil import mappings
from snakeoil.demandload import demandload

from . import __title__

demandload(
    'inspect',
    'pkgutil',
)

_reporoot = os.path.realpath(__file__).rsplit(os.path.sep, 3)[0]
# TODO: handle running from build dir inside repo in a better fashion
if _reporoot.endswith('/build'):
    _reporoot = os.path.dirname(_reporoot)
_module = sys.modules[__name__]
try:
    # This is a file written during installation;
    # if it exists, we defer to it. If it doesn't, then we're
    # running from a git checkout or a tarball.
    from . import _const as _defaults
except ImportError:
    _defaults = object()


def _GET_CONST(attr, default_value, allow_env_override=False):
    consts = mappings.ProxiedAttrs(_module)
    is_tuple = not isinstance(default_value, str)
    if is_tuple:
        default_value = tuple(x % consts for x in default_value)
    else:
        default_value %= consts

    result = getattr(_defaults, attr, default_value)
    # allow data path override for running tests against config files in the repo
    if allow_env_override:
        result = os.environ.get("BITE_OVERRIDE_%s" % attr, result)
    if is_tuple:
        result = tuple(result)
    return result


BROWSER = os.environ.get('BROWSER', 'xdg-open')
COLUMNS = get_terminal_size()[0]
DATA_PATH = _GET_CONST('DATA_PATH', _reporoot, allow_env_override=True)
CONFIG_PATH = _GET_CONST('CONFIG_PATH', '%(DATA_PATH)s/config')

# determine XDG compatible paths
for xdg_var, var_name, fallback_dir in (
        ('XDG_CONFIG_HOME', 'USER_CONFIG_PATH', '~/.config'),
        ('XDG_CACHE_HOME', 'USER_CACHE_PATH', '~/.cache'),
        ('XDG_DATA_HOME', 'USER_DATA_PATH', '~/.local/share')):
    setattr(_module, var_name,
            os.environ.get(xdg_var, os.path.join(os.path.expanduser(fallback_dir), __title__)))


def _service_cls(x):
    if inspect.isclass(x) and getattr(x, '_service', None) is not None:
        return True
    return False


def _find_service_classes(module_name, matcher=_service_cls):
    module = import_module(f'.{module_name}', __title__)
    classes = []
    for imp, name, _ in pkgutil.walk_packages(module.__path__, module.__name__ + '.'):
        # skip "private" modules
        if name.rsplit('.', 1)[1][0] == '_':
            continue
        try:
            m = import_module(name)
        except ImportError as e:
            raise Exception(f'failed importing {name!r}: {e}')
        for name, cls in inspect.getmembers(m, matcher):
            classes.append((cls._service, '.'.join([m.__name__, cls.__name__])))
    return classes


def _GET_VALS(attr, func):
    try:
        result = getattr(_defaults, attr)
    except AttributeError:
        result = func()
    return result


try:
    CLIENTS = mappings.ImmutableDict(_GET_VALS(
        'CLIENTS', partial(_find_service_classes, 'client')))
    SERVICES = mappings.ImmutableDict(_GET_VALS(
        'SERVICES', partial(_find_service_classes, 'service')))
    SERVICE_OPTS = mappings.ImmutableDict(_GET_VALS(
        'SERVICE_OPTS', partial(_find_service_classes, 'args')))
except SyntaxError as e:
    raise SyntaxError(f'invalid syntax: {e.filename}, line {e.lineno}')
