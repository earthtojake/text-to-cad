"""``cad.mujoco``: the mujoco integration -- our code that calls MuJoCo, taking its objects (its extra,
``cad[mujoco]``: ``mujoco-core``, the compiler and the Python bindings, numpy their one dependency, and
``mujoco-studio``, MuJoCo Studio's web viewer; no window system).

What it does for the MJCF document type (``cad.mjcf``): ``compile_findings`` compiles a model with
MuJoCo's own compiler and says what it refused, in its words, as findings (``cad mjcf validate
--compile``). Reading an MJCF for the viewer and the stills is the type's own (``cad.mjcf._source``),
the standard library alone: nothing here is needed to open one. ``cad run mujoco-studio --model FILE`` shows
the person a model in Studio's web viewer (``_command``: the environment's own ``mujoco-studio``).

Everything loads on first use: ``import cad.mujoco`` imports no mujoco. A helper called where the
extra is missing says so by name (``cad[mujoco]``), as every integration's does.
"""

from __future__ import annotations

__all__ = ["compile_findings", "compile_model"]


def compile_model(path):
    """The model at ``path`` compiled by MuJoCo (``mujoco.MjModel``), its compile warnings beside it, as
    ``(model, warnings)``; MuJoCo's ``ValueError`` for a model it refuses."""
    from cad.mujoco._compile import compile_model as _compile

    return _compile(path)


def compile_findings(path, *, mode="auto"):
    """Compile the MJCF at ``path`` with MuJoCo and answer findings (``cad._internal.findings.FindingsReport``):
    an error with MuJoCo's words for a model it refuses, a warning for each compile warning, an info saying the
    compile passed or was skipped (``mode`` ``auto``, mujoco not installed here); ``required`` without mujoco
    is an error naming the extra."""
    from cad.mujoco._compile import compile_findings as _findings

    return _findings(path, mode=mode)
