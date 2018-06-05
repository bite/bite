|test|

====
bite
====

bite is a bug, issue, and ticket extraction library and command-line tool. It
provides varying levels of support for numerous trackers based on what their
APIs support and/or what has been implemented so far.

CLI
===

Subcommands
-----------

At its simplest, bite supports searching and viewing tracker items of interest.

For example, to search for bugs assigned to myself::

    bite search -a radhermit

To get a specific bug via its ID::

    bite get 123456

See the related tracker service man pages for more service specific information
including what subcommands bite supports for the service and their options.

Services
--------

To view the list of supported bug, issue, and ticket trackers, run::

    bite ls services

These service IDs can be used to connect to unconfigured services directly on
the command-line similar to::

    bite --base https://bugzilla.mozilla.org --service bugzilla5.2-rest search bugzilla

which will search for upstream Bugzilla related bugs using Bugzilla-5.2's REST
API support.

Note that bite comes with many open source project trackers preconfigured as
named connections so the previous command can be more easily run as::

    bite -c mozilla search bugzilla

To see the list of preconfigured trackers use::

    bite ls connections

Installing
==========

Installing from git in a virtualenv::

    git clone https://github.com/bite/bite.git
    ./bite/requirements/pip.sh ./bite

Note that bite uses a shim script for running pip in order to gracefully handle
fallbacks to installing deps from git repos when the requested versions aren't
released yet.


.. |test| image:: https://travis-ci.org/bite/bite.svg?branch=master
    :target: https://travis-ci.org/bite/bite
