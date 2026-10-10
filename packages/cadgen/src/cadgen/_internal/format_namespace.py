"""Make a public format-namespace module callable as its own decorator.

``cadgen.step`` names two things that must be ONE thing: the ``@step``
declaration decorator and the ``step.build(...)`` verb namespace. Python gives
a package exactly one attribute per submodule name, so a separate
``cadgen/step.py`` module would shadow the decorator the moment anything
imported it — and ``from cadgen import step`` is the authoring API in every
model script.

Rebinding the module's ``__class__`` to a callable ``ModuleType`` subclass
resolves that with no ambiguity anywhere: ``@step`` decorates, ``step.build()``
operates, ``import cadgen.step`` and ``from cadgen import step`` return the
same object either way.

The decorator itself is imported lazily so the namespace module stays inside
the pre-gate import budget.
"""

from __future__ import annotations

import sys
from types import ModuleType
from typing import Any


def callable_namespace(module_name: str, decorator: str) -> None:
    """Bind ``sys.modules[module_name]`` to the ``cadgen.authoring`` decorator."""

    class FormatNamespace(ModuleType):
        def __call__(self, *args: Any, **kwargs: Any) -> Any:
            from cadgen import authoring

            return getattr(authoring, decorator)(*args, **kwargs)

    FormatNamespace.__name__ = f"{decorator.capitalize()}Namespace"
    sys.modules[module_name].__class__ = FormatNamespace
