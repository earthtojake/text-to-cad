"""The CAD Viewer's backend: ``cadgen viewer``.

A Python HTTP server for the built React client, serving every CAD file on this
machine by absolute path, on port 3245 or the one ``--port`` names, launched from
anywhere::

    cadgen viewer        # or: python -m cadgen.viewer

The client is built from ``apps/web`` in the source repository and ships in
the wheel under ``cadgen/_runtime/viewer`` (see ``cadgen.assets.viewer_dist_dir``).

Nothing in this package may import the CAD kernel (OCP, build123d) at module
scope. ``cadgen viewer`` must start in the time ``cadgen --help`` does, and a
long-lived server must not hold ~300MB of kernel it never uses: the one
kernel-bearing action, compiling a document whose bytes have no tree, is a
compile job in cadgen's build pool (``compiles``; a daemon spare or a transient
subprocess), never this
process. ``tests/python/packages/cadgen/viewer/test_module_boundaries.py``
holds the line.
"""
