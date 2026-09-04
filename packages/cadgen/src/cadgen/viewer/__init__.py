"""The CAD Viewer's backend: ``cadgen viewer``.

A Python HTTP server for the built React client, launched from the directory it
should serve (the cwd IS the served directory)::

    cd /absolute/dir && cadgen viewer        # or: python -m cadgen.viewer

The client is built from ``apps/viewer`` in the source repository and ships in
the wheel under ``cadgen/_runtime/viewer`` (see ``cadgen.assets.viewer_dist_dir``).

Nothing in this package may import the CAD kernel (OCP, build123d) at module
scope. ``cadgen viewer`` must start in the time ``cadgen --help`` does, and a
long-lived server must not hold ~300MB of kernel it never uses: the one
kernel-bearing action, importing a foreign STEP, is a compile job in cadgen's
build pool (``imports``; a daemon spare or a transient subprocess), never this
process. ``tests/python/packages/cadgen/viewer/test_module_boundaries.py``
holds the line.
"""
