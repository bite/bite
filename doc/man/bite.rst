====
bite
====

.. include:: ../generated/bite/_synopsis.rst
.. include:: ../generated/bite/_description.rst
.. include:: ../generated/bite/_options.rst
.. include:: ../generated/bite/_subcommands.rst

Aliases
=======

bite supports command aliases similar to shells, git, and related command-line
tools.

Some simple subcommand aliases are enabled by bite's system config allowing for
quicker usage. For example, searching can be done using the 's' alias::

    bite s term

and retrieving items using 'g'::

    bite g 123456

Alias precedence
----------------

Note that any system level alias will be overridden by matching user aliases.

Advanced aliases
----------------

bite supports more advanced, dynamic forms of aliases that use
shell functions or interpolate values from different config sections. See the
man page for more details.

Interpolation
~~~~~~~~~~~~~

Aliases can interpolate values from different config sections.

Shell functions
~~~~~~~~~~~~~~~

TODO

Example Usage
=============

TODO

Reporting Bugs
==============

Please submit an issue via github:

https://github.com/bite/bite/issues
