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

Aliases
-------

Similar to shells, git, and similar tools, bite supports command aliases. Some
simple subcommand aliases are enabled by bite's system config allowing for
quicker usage. For example, the previous subcommand examples can be simplified
to searching via::

    bite s -a radhermit

and retrieving items with::

    bite g 123456

Note that any system level alias will be overridden by matching user aliases.
See the bite man page for more information about alias precendence resolution
in relation to services.

Additionally, bite supports more advanced, dynamic forms of aliases that use
shell functions or interpolate values from different config sections. See the
man page for more details.

Services
--------

To view the list of supported bug, issue, and ticket trackers, run::

    bite ls services

These service IDs can be used to connect to unconfigured services directly on
the command-line similar to::

    bite --base https://bugzilla.mozilla.org --service bugzilla5.2-jsonrpc search bugzilla

which will search for upstream Bugzilla related bugs.

Note that many open source trackers have already been registered in bite itself
so the previous command can be more easily run as::

    bite -c mozilla search bugzilla

To see the list of pre-configured trackers use::

    bite ls connections


.. |test| image:: https://travis-ci.org/bite/bite.svg?branch=master
    :target: https://travis-ci.org/bite/bite
