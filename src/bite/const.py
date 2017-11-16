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

BROWSER = os.environ.get('BROWSER', 'xdg-open')
COLUMNS = get_terminal_size()[0]
DATA_PATH = _GET_CONST('DATA_PATH', _reporoot)
if CONFIG_PATH is None:
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

def _clients():
    from . import client
    clients = []
    for imp, name, _ in pkgutil.walk_packages(client.__path__, client.__name__ + '.'):
        module = imp.find_module(name).load_module()
        for name, cls in inspect.getmembers(module, _service_cls):
            clients.append((cls._service, '.'.join([module.__name__, cls.__name__])))
    return clients

def _services():
    from . import service
    services = []
    for imp, name, _ in pkgutil.walk_packages(service.__path__, service.__name__ + '.'):
        module = imp.find_module(name).load_module()
        for name, cls in inspect.getmembers(module, _service_cls):
            services.append((cls._service, '.'.join([module.__name__, cls.__name__])))
    return services

def _GET_CLIENTS(attr, func):
    try:
        result = getattr(_defaults, attr)
    except AttributeError:
        result = func()
    return result

def _GET_SERVICES(attr, func):
    try:
        result = getattr(_defaults, attr)
    except AttributeError:
        result = func()
    return result

CLIENTS = mappings.ImmutableDict(_GET_CLIENTS('CLIENTS', _clients))
SERVICES = mappings.ImmutableDict(_GET_SERVICES('SERVICES', _services))
