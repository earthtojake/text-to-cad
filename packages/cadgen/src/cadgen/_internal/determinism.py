"""Make build123d's shape de-duplication order a function of CONTENT, not heap layout.

``Shape.__hash__`` is ``hash(self.wrapped)``, and OCCT hashes a ``TopoDS_Shape``
from its ``TShape`` POINTER. Every ``set()`` of shapes therefore iterates in
heap-address order: the same model, built twice, hands its downstream geometry
constructors the same shapes in a different sequence. Most of the time that is
invisible, but where the order picks a direction (``Edge.make_line(*two_vertices)``)
or seeds an intersection chain, it lands in the BREP bytes — and those bytes are
cadgen's content-addressed component ids. A model that re-keys its components on
every build defeats the whole component cache, and no amount of memoization above
it can help.

The fix keeps set SEMANTICS (dedup by ``is_same``, which is what ``Shape.__eq__``
does) and drops only the address-derived ORDER, by keeping first occurrence.
Two independent mechanisms, because the two families of site are reached
differently:

* ``ShapeList(set(...))`` — nine sites across three topology modules. A module-
  global ``set`` shadows the builtin for those modules ONLY when handed a
  ``ShapeList``; anything else falls straight through to ``builtins.set``, so
  no unrelated set in those modules changes behaviour.
* ``{ve for e in edges for ve in e.vertices() if ve != vertex}`` in
  ``FilletPolyline`` — a set COMPREHENSION compiles to inline bytecode with no
  ``set`` call to shadow. Instead ``Vertex.__hash__`` uses the same live native
  coordinates and rounding as the op memo's geometric identity. With the memo
  disabled, pointer-distinct vertices may share a bucket; pointer equality
  still separates them. Reading OCCT again also observes native point and
  location edits that leave build123d's cached ``X``/``Y``/``Z`` unchanged.

``CADGEN_DETERMINISM=0`` disables both. ``install()`` is idempotent and never
raises: build123d is an external dependency, so a version whose shape does not
match is left alone rather than guessed at — the worst case is the old
nondeterminism, never a wrong build.
"""

from __future__ import annotations

import builtins
import os
from typing import Any, Iterable

# The topology modules whose `ShapeList(set(...))` de-duplications lose order.
# build_common.py has the same pattern at one site but also does
# `isinstance(item, (list, tuple, filter, set))`, which a shadowed `set` would
# break -- so it is deliberately NOT in this list.
_SHADOWED_MODULES = (
    "build123d.topology.shape_core",
    "build123d.topology.composite",
    "build123d.topology.three_d",
)

_MISSING = object()
_installed = False


class OrderedShapeSet:
    """A set of shapes that iterates in first-occurrence order.

    Membership, and therefore de-duplication, uses the ordinary
    ``__hash__``/``__eq__`` of the elements: the address-derived hash is a
    perfectly good bucket key WITHIN one process, and this class never lets it
    decide an order. Only the operators the shadowed sites actually use are
    implemented (``&``, ``-``, ``|``, ``==``, ``!=``, iteration, length,
    membership); anything else is deliberately absent so an unanticipated use
    fails loudly instead of silently differing from a real set."""

    __slots__ = ("_items", "_seen")

    def __init__(self, items: Iterable[Any] = ()) -> None:
        self._items: list[Any] = []
        self._seen = builtins.set()
        for item in items:
            if item not in self._seen:
                self._seen.add(item)
                self._items.append(item)

    def __iter__(self):
        return iter(self._items)

    def __len__(self) -> int:
        return len(self._items)

    def __contains__(self, item: Any) -> bool:
        return item in self._seen

    def __bool__(self) -> bool:
        return bool(self._items)

    def __and__(self, other: Any) -> "OrderedShapeSet":
        return OrderedShapeSet([item for item in self._items if item in other])

    def __rand__(self, other: Any) -> "OrderedShapeSet":
        return OrderedShapeSet([item for item in other if item in self._seen])

    def __sub__(self, other: Any) -> "OrderedShapeSet":
        return OrderedShapeSet([item for item in self._items if item not in other])

    def __rsub__(self, other: Any) -> "OrderedShapeSet":
        return OrderedShapeSet([item for item in other if item not in self._seen])

    def __or__(self, other: Any) -> "OrderedShapeSet":
        return OrderedShapeSet(list(self._items) + list(other))

    __ror__ = __or__

    def __eq__(self, other: Any) -> Any:
        if isinstance(other, OrderedShapeSet):
            return self._seen == other._seen
        if isinstance(other, (builtins.set, frozenset)):
            return self._seen == other
        return NotImplemented

    def __ne__(self, other: Any) -> Any:
        result = self.__eq__(other)
        return result if result is NotImplemented else not result

    def __hash__(self):  # a set is unhashable; match that
        raise TypeError("unhashable type: 'OrderedShapeSet'")

    def __repr__(self) -> str:
        return f"OrderedShapeSet({self._items!r})"


def _make_ordered_set(shape_list_cls: type) -> Any:
    """The ``set`` stand-in installed into a build123d topology module.

    Narrow on purpose: it diverts ONLY ``set(<ShapeList>)``. Every other call in
    the shadowing module -- ``set()``, ``set(dict.keys())``, ``set(tuple)`` --
    returns a genuine builtin set, so shadowing the name cannot change the
    behaviour of code this module was not written for."""

    def ordered_set(iterable: Any = _MISSING) -> Any:
        if iterable is _MISSING:
            return builtins.set()
        if isinstance(iterable, shape_list_cls):
            return OrderedShapeSet(iterable)
        return builtins.set(iterable)

    ordered_set.__name__ = "set"
    ordered_set.__qualname__ = "set"
    return ordered_set


def _vertex_hash(self: Any) -> int:
    """Hash the current native point at geometric equality's precision.

    With the op memo enabled, a Vertex and another Shape wrapper of that native
    vertex agree too. No point or signature is retained between calls.
    """
    if self._wrapped is None:
        return 0
    from cadgen._internal.op_memo import _signature_hash

    try:
        return _signature_hash(self.wrapped)
    except Exception:
        return hash(self.wrapped)


def install() -> bool:
    """Install the shims. Idempotent; returns True when they are active.

    Called from the generator runner beside ``op_memo.install()`` so every
    model execution -- cold CLI or warm daemon worker -- builds against the
    same ordering rules. Import failures and unexpected module shapes leave
    build123d untouched."""
    global _installed
    if _installed:
        return True
    if os.environ.get("CADGEN_DETERMINISM", "").strip() == "0":
        return False
    try:
        import importlib

        from build123d.topology.shape_core import ShapeList
        from build123d.topology.zero_d import Vertex
    except Exception:  # noqa: BLE001 - an unexpected build123d is left alone
        return False

    for module_name in _SHADOWED_MODULES:
        try:
            module = importlib.import_module(module_name)
        except Exception:  # noqa: BLE001
            continue
        # Only shadow a name the module does not already define itself; if a
        # future build123d binds `set` for its own purposes, step aside.
        if "set" in vars(module):
            continue
        setattr(module, "set", _make_ordered_set(ShapeList))

    if getattr(Vertex.__hash__, "__name__", "") != "_vertex_hash":
        Vertex.__hash__ = _vertex_hash  # type: ignore[method-assign]

    _installed = True
    return True
