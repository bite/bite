#!/usr/bin/env python

import os
from glob import glob

from setuptools import setup, find_packages

import pkgdist


setup(
    name='bite',
    description='Bug, issue, and ticket extraction tool',
    version=pkgdist.version(),
    author='Tim Harder',
    author_email='radhermit@gmail.com',
    url='https://github.com/radhermit/bite/',
    license='BSD',
    platforms=['any'],
    packages=find_packages(),
    scripts=os.listdir('bin'),
    install_requires=['requests>=2', 'python-dateutil>=2.1'],
    data_files=[
        ('share/bite/services', glob('config/services/*')),
    ],
    cmdclass={
        'build_scripts': pkgdist.build_scripts,
        'sdist': pkgdist.sdist,
    },
    classifiers=[
        'Intended Audience :: Developers',
        'License :: OSI Approved :: BSD License',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
    ],
)
