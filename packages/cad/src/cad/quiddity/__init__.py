"""``cad.quiddity``: the quiddity integration -- our code that asks quiddity, Paul Fremantle's feature recogniser, about
one part of a document (its extra, ``cad[quiddity]``: the ``quiddity`` wheel, a Rust library with no dependency
of its own, Apache-2.0).

quiddity reads a STEP and says the features it finds -- holes, pockets, slots, fillets and the rest -- each with
the faces it is made of, and where every face went. It always runs in a process of its own (``_process``, which
starts it, says where quiddity is and why it is never imported beside the kernel; ``_recogniser``, the one module
that imports quiddity; ``_frames``, what crosses the pipe between them): a part it has not answered in time is
given up and its process stopped, and nothing it does reaches the process that asked. Nothing of the tool is
re-exported, and ``import cad.quiddity`` imports no quiddity.
"""
