__title__ = 'bite'
__version__ = '0.0.3'

from importlib import import_module

from . import const

from bitelib.exceptions import BiteError

def get_client(service):
    """Return the CLI class for a related service."""
    try:
        mod_name, cls_name = const.SERVICES[service].rsplit('.', 1)
    except KeyError:
        raise BiteError('invalid service: {!r}\n(available services: {})'.format(
            service, ', '.join(sorted(const.SERVICES))))
    return getattr(import_module(mod_name), cls_name)
