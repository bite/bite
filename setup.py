#!/usr/bin/env python

from glob import glob

from setuptools import setup

import pkgdist
pkgdist_setup, pkgdist_cmds = pkgdist.setup()


setup(
    description='Bug, issue, and ticket extraction tool',
    author='Tim Harder',
    author_email='radhermit@gmail.com',
    url='https://github.com/radhermit/bite/',
    license='BSD',
    platforms=['any'],
    data_files=[
        ('share/bite/services', glob('config/services/*')),
    ],
    cmdclass=dict(**pkgdist_cmds),
    classifiers=(
        'Intended Audience :: Developers',
        'License :: OSI Approved :: BSD License',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
    ),
    **pkgdist_setup
)
