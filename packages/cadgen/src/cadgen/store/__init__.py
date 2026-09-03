"""The cadgen store: every model's result, one way.

Layout (``STORE.md`` is the full account; read it before changing anything here)::

    <store root>/
      objects/ab/cdef…        immutable, content-addressed: components and trees
      index/model/<key>       records — one per model, keyed by its script path
      index/op/<key>          op-memo entries -> object hash
      index/mesh/<key>        tessellation entries -> object hash

A **model** is a parameterless ``@step`` function; its identity is its resolved
script path. Its result is a **tree** object: the components it made itself plus
**links** to its children's trees. Its **record** says which tree is current, what
closure produced it, which children it pinned, and what outputs it wrote.

Everything in ``objects/`` is content-addressed and never rewritten; everything in
``index/`` is small JSON written temp + rename. No directories per result, no
hardlinks, no staging dirs, no version salts. Outputs (the ``.step``, its sidecar,
declared mesh files) live in the project, not here.
"""

from cadgen.store.index import model_key, read_entry, write_entry
from cadgen.store.objects import has_object, object_path, put_object, read_object
from cadgen.store.paths import index_dir, objects_dir, store_root
from cadgen.store.records import read_record, record_for_document, write_record
from cadgen.store.trees import flatten, get_tree, put_tree

__all__ = [
    "flatten",
    "get_tree",
    "has_object",
    "index_dir",
    "model_key",
    "object_path",
    "objects_dir",
    "put_object",
    "put_tree",
    "read_entry",
    "read_object",
    "read_record",
    "record_for_document",
    "store_root",
    "write_entry",
    "write_record",
]
