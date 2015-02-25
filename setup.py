from bite import __version__

from setuptools import setup, find_packages

setup(
    name='bite',
    description='Bug, issue, and ticket extraction utility',
    version=__version__,
    author='Tim Harder',
    author_email='radhermit@gmail.com',
    url='https://github.com/radhermit/bite/',
    license='BSD',
    platforms=['any'],
    packages=find_packages(),
    scripts=['bin/bite'],
    install_requires=['requests>=2', 'python-dateutil>=2.1'],
    classifiers=[
        'Programming Language :: Python :: 3.3',
        'Programming Language :: Python :: 3.4',
    ],
)
