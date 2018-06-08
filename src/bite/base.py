from importlib import import_module
import re

from snakeoil.demandload import demandload

from .exceptions import BiteError

demandload(
    'bite:const,service',
    'bite.config:Config',
)


def get_service_cls(service_name, options, fallbacks=()):
    """Return the class for a given, supported service type."""
    # support getting passed service objects and service name strings
    if isinstance(service_name, service.Service):
        service_name = getattr(service_name, '_service')

    try:
        mod_name, cls_name = options[service_name].rsplit('.', 1)
    except KeyError:
        for i, fallback in enumerate(fallbacks, start=1):
            # if fallback is a class, use it
            if isinstance(fallback, type):
                return fallback
            # if fallback is True, inject service fallbacks automatically
            elif fallback is True and not any((x is True for x in fallbacks[i:])):
                fallbacks = tuple(service_classes(service_name))[1:] + tuple(fallbacks[i:])
                return get_service_cls(fallbacks[0], options, fallbacks=fallbacks[1:])
            # otherwise try to find matching fallback class
            elif isinstance(fallback, str):
                return get_service_cls(fallback, options, fallbacks=fallbacks[i:])
        raise BiteError(
            f'invalid service: {service_name!r}\n'
            f"(available services: {', '.join(sorted(options))})")

    return getattr(import_module(mod_name), cls_name)


def get_service(connection, **kw):
    """Return a service object for a configured service or generic service type."""
    # support getting passed service objects and service name strings
    args = {}
    try:
        config = Config(connection=connection)
        args.update(config.items(connection))
        service_cls = get_service_cls(args['service'], const.SERVICES)
    except BiteError:
        # assume it's an actual service class name
        try:
            service_cls = get_service_cls(connection, const.SERVICES)
        except BiteError:
            raise BiteError(f'unknown connection or service name: {connection!r}') from None

    args.update(kw)
    return service_cls(**args)


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
