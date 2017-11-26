#!/usr/bin/env python

import errno
from itertools import chain
import os
import sys

from distutils import log
from distutils.util import byte_compile
from setuptools import setup

import pkgdist
pkgdist_setup, pkgdist_cmds = pkgdist.setup()

# These offsets control where we install the config and service files.
DATA_INSTALL_OFFSET = os.path.join('share', pkgdist.MODULE)
CONFIG_INSTALL_OFFSET = os.path.join(DATA_INSTALL_OFFSET, 'config')


class install(pkgdist.install):
    """Install wrapper to generate and install lookup files."""

    def run(self):
        pkgdist.install.run(self)
        target = self.install_data
        root = self.root or '/'
        if target.startswith(root):
            target = os.path.join('/', os.path.relpath(target, root))
        target = os.path.abspath(target)
        if not self.dry_run:
            # Install configuration data so the program can find its content,
            # rather than assuming it is running from a tarball/git repo.
            write_lookup_config(self.install_purelib, target)


def write_lookup_config(python_base, install_prefix):
    """Generate file of install path constants."""
    path = os.path.join(python_base, pkgdist.MODULE, "_const.py")
    try:
        os.makedirs(os.path.dirname(path))
    except OSError as e:
        if e.errno != errno.EEXIST:
            raise
    log.info("writing lookup config to %r" % path)

    with pkgdist.syspath(pkgdist.PACKAGEDIR):
        from bite import const
    clients = tuple(sorted(const.CLIENTS.items()))
    services = tuple(sorted(const.SERVICES.items()))
    service_opts = tuple(sorted(const.SERVICE_OPTS.items()))

    import textwrap
    with open(path, "w") as f:
        os.chmod(path, 0o644)
        # write more dynamic file for wheel installs
        if install_prefix != os.path.abspath(sys.prefix):
            f.write(textwrap.dedent("""\
                import os.path as osp
                import sys

                INSTALL_PREFIX = osp.abspath(sys.prefix)
                DATA_PATH = osp.join(INSTALL_PREFIX, {!r})
                CONFIG_PATH = osp.join(INSTALL_PREFIX, {!r})

                CLIENTS = {}
                SERVICES = {}
                SERVICE_OPTS = {}
            """.format(
                DATA_INSTALL_OFFSET, CONFIG_INSTALL_OFFSET,
                clients, services, service_opts)))
        else:
            f.write(textwrap.dedent("""\
                INSTALL_PREFIX = {!r}
                DATA_PATH = {!r}
                CONFIG_PATH = {!r}

                CLIENTS = {!r}
                SERVICES = {!r}
                SERVICE_OPTS = {!r}
            """.format(
                install_prefix,
                os.path.join(install_prefix, DATA_INSTALL_OFFSET),
                os.path.join(install_prefix, CONFIG_INSTALL_OFFSET),
                clients, services, service_opts)))

            f.close()
            byte_compile([path], prefix=python_base)
            byte_compile([path], optimize=2, prefix=python_base)


setup(
    description='bug, issue, and ticket extraction library and command line tool',
    author='Tim Harder',
    author_email='radhermit@gmail.com',
    url='https://github.com/radhermit/bite/',
    license='BSD',
    platforms=['any'],
    data_files=list(chain(
        pkgdist.data_mapping(CONFIG_INSTALL_OFFSET, 'config'),
        pkgdist.data_mapping(os.path.join(DATA_INSTALL_OFFSET, 'services'), 'services'),
    )),
    cmdclass=dict(
        pkgdist_cmds,
        install=install,
        test=pkgdist.pytest),
    classifiers=(
        'Intended Audience :: Developers',
        'License :: OSI Approved :: BSD License',
        'Programming Language :: Python :: 3.6',
    ),
    **pkgdist_setup
)
