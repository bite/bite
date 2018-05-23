from importlib import import_module

from snakeoil.demandload import demandload

from .config import load_service_files
from .exceptions import BiteError

demandload('bite:const')

__title__ = 'bite'
__version__ = '0.0.1'


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


def get_service(connection):
    """Return a service object for a configured service."""
    # support getting passed service objects and service name strings
    config = load_service_files(connection)

    if not config.has_section(connection):
        raise BiteError(f'unknown connection: {connection!r}')

    args = dict(config.items(connection))
    service_obj = get_service_cls(args['service'], const.SERVICES)(**args)
    return service_obj
