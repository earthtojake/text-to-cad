"""The plugin in the agent apps: the one place in cad that names an agent app, a plugin or a skill.

Everything else in cad says what cad does without those words (as ``cad_server.mcp`` is the one place that knows the
host). This package is reached only by the ``cad plugin`` command (``cad_server.cli.plugin``): ``cad plugin install``
(and ``cad plugin update``, its hidden second name) runs it (``run.install``); nothing else in cad imports it, and it
runs no install command, hosted or other, never cad's own update, and never cad itself.

- ``computer``: this computer as a run sees it (``Here``), a command run and stopped at its time, a person's config
  read whatever its shape, and nothing removed or replaced by half.
- ``source``: where the plugin comes from (the GitHub repository's ``latest`` branch, or a checkout's folder), our
  names, and how a copy says it is ours.
- ``apps``: ``APPS``, the one table of apps -- how each is found, how ours is installed and updated there, how our old
  copies are found and removed --, and every app done in turn (``install_apps``).
- ``terminal``: what a person's terminal gets on top of the plain lines: the logo, the live line, the marks.
- ``run``: one run, under the lock that keeps it the only one, and what it was (``run.Facts``).

The standard library alone but for ``run``, which asks cad for the lock (``cad_server._internal.plugin_catch_up``)
and gives the other modules cad's one rename (``cad._internal.atomic_replace``).
Every module is imported before a run begins (``cad_server.cli.plugin``, and here but for ``run``): an update of cad
may replace this environment's files under a running process, and a module imported later would be another
release's. A checkout's development install loads these modules by their files, without cad; so they import each
other relatively, and ``run`` is not imported here.
"""

from . import apps, computer, source, terminal  # noqa: F401 - imported up front (see above)
