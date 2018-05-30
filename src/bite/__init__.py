from importlib import import_module
import re

from snakeoil.demandload import demandload

from .config import load_service_files
from .exceptions import BiteError

demandload('bite:const')

__title__ = 'bite'
__version__ = '0.0.1'


def get_service_cls(service_name, options, fallbacks=()):
    """Return the class for a given, supported service type."""
    # support getting passed service objects and service name strings
    if isinstance(service_name, type):
        service_name = getattr(service_name, '_service')

    try:
        mod_name, cls_name = options[service_name].rsplit('.', 1)
    except KeyError:
        for i, fallback in enumerate(fallbacks, start=1):
            # if fallback is a class, use it
            if isinstance(fallback, type):
                return fallback
            # otherwise try to find matching fallback class
            elif isinstance(fallback, str):
                return get_service_cls(fallback, options, fallbacks=fallbacks[i:])
        raise BiteError('invalid service: {!r}\n(available services: {})'.format(
            service_name, ', '.join(sorted(options))))

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


def service_classes(service_name):
    """Generator for service classes from specific to generic.

    Service types yielded in order if they exist:
        - full service name
        - protocol agnostic and/or versioned services (can be multiple)
        - generic nonversioned service

    For example, with bugzilla5.0-jsonrpc passed in this will yield
    bugzilla5.0-jsonrpc, bugzilla5.0, and bugzilla, respectively.
    """
    if service_name:
        yield service_name
        while True:
            base_service, _sep, _specific = service_name.rpartition('-')
            if not _sep:
                break
            yield base_service
            service_name = base_service
        service_match = re.match(r'([a-z]+)[\d.]+', service_name)
        if service_match:
            yield service_match.group(1)
