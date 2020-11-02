#!/usr/bin/env python3

from distutils import log
from distutils.util import byte_compile
from itertools import chain
import os
import sys
from textwrap import dedent

from setuptools import setup

from snakeoil.dist import distutils_extensions as pkgdist
pkgdist_setup, pkgdist_cmds = pkgdist.setup()

# These offsets control where we install the config and service files.
DATA_INSTALL_OFFSET = os.path.join('share', pkgdist.MODULE_NAME)
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
    path = os.path.join(python_base, pkgdist.MODULE_NAME, "_const.py")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    log.info("writing lookup config to %r" % path)

    with pkgdist.syspath(pkgdist.PACKAGEDIR):
        from bite import const
    clients = tuple(sorted(const.CLIENTS.items()))
    services = tuple(sorted(const.SERVICES.items()))
    service_opts = tuple(sorted(const.SERVICE_OPTS.items()))

    with open(path, "w") as f:
        os.chmod(path, 0o644)
        # write more dynamic file for wheel installs
        if install_prefix != os.path.abspath(sys.prefix):
            f.write(dedent(f"""\
                import os.path as osp
                import sys

                INSTALL_PREFIX = osp.abspath(sys.prefix)
                DATA_PATH = osp.join(INSTALL_PREFIX, {DATA_INSTALL_OFFSET!r})
                CONFIG_PATH = osp.join(INSTALL_PREFIX, {CONFIG_INSTALL_OFFSET!r})

                CLIENTS = {clients}
                SERVICES = {services}
                SERVICE_OPTS = {service_opts}
            """))
        else:
            data_path = os.path.join(install_prefix, DATA_INSTALL_OFFSET)
            config_path = os.path.join(install_prefix, CONFIG_INSTALL_OFFSET)
            f.write(dedent(f"""\
                INSTALL_PREFIX = {install_prefix!r}
                DATA_PATH = {data_path!r}
                CONFIG_PATH = {config_path!r}

                CLIENTS = {clients!r}
                SERVICES = {services!r}
                SERVICE_OPTS = {service_opts!r}
            """))

            f.close()
            byte_compile([path], prefix=python_base)
            byte_compile([path], optimize=1, prefix=python_base)
            byte_compile([path], optimize=2, prefix=python_base)


class test(pkgdist.pytest):
    """Test wrapper to enforce testing against built version."""

    def run(self):
        # This is fairly hacky, but is done to ensure that the tests
        # are ran purely from what's in build, reflecting back to the source
        # only for misc bash scripts or config data.
        key = 'BITE_OVERRIDE_DATA_PATH'
        original = os.environ.get(key)
        try:
            os.environ[key] = os.path.dirname(os.path.realpath(__file__))
            return super().run()
        finally:
            if original is not None:
                os.environ[key] = original
            else:
                os.environ.pop(key, None)


setup(
    description='bug, issue, and ticket extraction library and command line tool',
    author='Tim Harder',
    author_email='radhermit@gmail.com',
    url='https://github.com/bite/bite/',
    license='BSD',
    platforms=['any'],
    data_files=list(chain(
        pkgdist.data_mapping(CONFIG_INSTALL_OFFSET, 'config'),
        pkgdist.data_mapping(os.path.join(DATA_INSTALL_OFFSET, 'services'), 'services'),
    )),
    cmdclass=dict(
        pkgdist_cmds,
        install=install,
        test=test),
    classifiers=[
        'Intended Audience :: Developers',
        'License :: OSI Approved :: BSD License',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
    ],
    **pkgdist_setup
)
