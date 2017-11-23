__title__ = 'bite'
__version__ = '0.0.3'

from importlib import import_module

from .exceptions import BiteError


def get_service_cls(service, options):
    """Return the class for a given, supported service type."""
    # support getting passed service objects and service name strings
    service = getattr(service, '_service', service)
    try:
        mod_name, cls_name = options[service].rsplit('.', 1)
    except KeyError:
        raise BiteError('invalid service: {!r}\n(available services: {})'.format(
            service, ', '.join(sorted(options))))
    return getattr(import_module(mod_name), cls_name)


