#!/usr/bin/env python3

from importlib import import_module
import os
import sys

from snakeoil.dist.generate_man_rsts import ManConverter

from bite.argparser import ArgumentParser
from bite.config import load_service_files
from bite.const import SERVICES, SERVICE_OPTS


def get_service_cls(service_name, dct):
    for name, mod in dct.items():
        if name.startswith(service_name):
            return mod
    else:
        raise ValueError(f"unknown service: {service_name!r}")


def main(f, docdir, gendir):
    service_name = os.path.basename(__file__).rsplit('.', 1)[0]
    try:
        service_mod = SERVICES[service_name]
        service_opts_mod = SERVICE_OPTS[service_name]
    except KeyError:
        service_name = service_name.replace('_', '.')
        service_mod = get_service_cls(service_name, SERVICES)
        service_opts_mod = get_service_cls(service_name, SERVICE_OPTS)

    parser = ArgumentParser(suppress=True)
    config = load_service_files(user_dir=False)

    mod_name, cls_name = service_mod.rsplit('.', 1)
    for connection in config.sections():
        args = dict(config.items(connection))
        if args['service'].startswith(service_name):
            break
    else:
        raise ValueError(f"no matching connection for service: {service_name!r}")
    service = getattr(import_module(mod_name), cls_name)(**args)
    mod_name, cls_name = service_opts_mod.rsplit('.', 1)
    service_opts = getattr(import_module(mod_name), cls_name)(parser, service_name)
    # pull docs from service opts class to fill out man page description
    parser._update_desc(service_opts.__doc__)

    service_opts.add_subcmd_opts(service=service, subcmd='_all_')
    ManConverter(gendir, service_name, parser, out_name=service_name).run()


if __name__ == '__main__':
    main()
