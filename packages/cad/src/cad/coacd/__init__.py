"""``cad.coacd``: the coacd integration -- our code that calls CoACD, the approximate convex decomposition of a
triangle mesh (its extra, ``cad[coacd]``: the ``coacd`` wheel, numpy its one dependency, MIT).

What it does for a robot description: a part declared ``collision(part, "decomposed")`` collides as the convex
hulls CoACD cuts its mesh into, while its visual stays whole (``cad.engine.describe``). The decomposer
(``_decomposer``) always runs in a process of its own, started by the engine (``cad.engine.hulls``, which keeps
the hulls in its cache by the mesh's digest and the options): CoACD's library carries a threading runtime (TBB)
of its own beside the kernel's, prints from native code and can die on a mesh it cannot repair, none of which
may reach the process that holds the kernel. Nothing of the tool is re-exported, and ``import cad.coacd``
imports no coacd.
"""
