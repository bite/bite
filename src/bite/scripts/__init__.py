#!/usr/bin/env python3

"""Wrapper for running commandline scripts."""

from importlib import import_module
import os
import sys


def run(script_name):
    """Run a given script module."""
    # Remove the current working directory to avoid implicit
    # namespace package (PEP 420) imports due to directories
    # matching module names.
    try:
        sys.path.remove(os.getcwd())
    except ValueError:
        pass

    try:
        from snakeoil import demandimport
        demandimport.enable()
        from bite.argparser import Tool
        script_module = '.'.join(
            os.path.realpath(__file__).split(os.path.sep)[-3:-1] +
            [script_name.replace('-', '_')])
        script = import_module(script_module)
    except ImportError as e:
        sys.stderr.write(f'Failed importing: {e}!\n')
        py_version = '.'.join(map(str, sys.version_info[:3]))
        sys.stderr.write(
            'Verify that bite and its deps are properly installed '
            f'and/or PYTHONPATH is set correctly for python {py_version}.\n')
        if '--debug' in sys.argv[1:]:
            raise
        sys.stderr.write('Add --debug to the commandline for a traceback.\n')
        sys.exit(1)

    tool = Tool(script.argparser)
    sys.exit(tool())


if __name__ == '__main__':
    # We're in a git repo or tarball so add the src dir to the system path.
    # Note that this assumes a certain module layout.
    src_dir = os.path.realpath(__file__).rsplit(os.path.sep, 3)[0]
    sys.path.insert(0, src_dir)
    run(os.path.basename(__file__))
