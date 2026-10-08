"""Lazy, transparent re-export of build123d.

The canonical model-script import is::

    from cadgen import build123d as bd

This module is a PEP 562 proxy: the first attribute touch performs the real
``import build123d`` (~2.5s cold — measured) and returns the GENUINE object,
which is then cached into this module's globals so every later access is a
plain attribute read. There are no wrapper objects anywhere: ``bd.Box`` IS
build123d's ``Box``, so isinstance, subclassing, ``except`` clauses and
identity checks all behave exactly as they would on the real module.

Why lazy: a model script's module body must stay featherweight so the
``@step`` decorator can gate (freshness check) and dispatch (warm daemon)
BEFORE any OCP cost is paid. On the warm path the invoking process never
resolves a single attribute; on a skipped (current) build nothing resolves at
all, so even daemonless no-op re-runs stay fast.

This is a TRANSPARENT re-export by design rule: same names, same signatures,
never "improved" — agents' build123d knowledge must transfer 1:1.

Note: ``from cadgen.build123d import Box`` works but is EAGER (a from-import
must bind the object, which forces the real import immediately). Attribute
style is the idiom that keeps the laziness.
"""

from __future__ import annotations

from typing import Any

_REAL = None


def _real_module():
    global _REAL
    if _REAL is None:
        import build123d as _build123d

        _REAL = _build123d
    return _REAL


def __getattr__(name: str) -> Any:
    if name.startswith("__") and name.endswith("__"):
        # Dunders reaching module __getattr__ are introspection probes
        # (__path__, __all__, ...); never trigger the heavy import for them.
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    real = _real_module()
    try:
        value = getattr(real, name)
    except AttributeError:
        # A name build123d does not have is the model's mistake, said at a raise as cadgen says
        # every mistake of the person's (``cadgen.analytics``: no crash of cadgen's). ``name`` and
        # ``obj`` keep Python's "Did you mean" suggestion, from build123d's own names.
        raise AttributeError(f"module 'build123d' has no attribute {name!r}", name=name, obj=real) from None
    globals()[name] = value  # steady state: ordinary attribute access
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(dir(_real_module())))
