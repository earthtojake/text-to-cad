"""``empty_operation``: an operation whose toolpath cuts nothing (rapids alone, or no moves at all).

A planner that cannot cut its feature says so itself (a :class:`~cadgen._internal.cam.job_errors.PlanError` of kind
``empty_operation``, ``tool_too_large``, ...); this is the net under every planner: an operation the job asked for
that put no cutting move in the program is never a silent row. One that names its target (``faces`` or a
``region``) is an error: the feature it was asked to make would be missing from the part. One that names none (a
facing pass over stock already flat) is a warning: it moves the tool and cuts nothing, which cannot crash or scrap.
From the parallel cam build.
"""

from __future__ import annotations

from cadgen._internal.cam.checks.base import finding

__all__ = ["run"]


def run(ctx) -> list[dict]:
    from cadgen._internal.cam.ir import DWELL, RAPID

    out = []
    for op in ctx.ops:
        if "plan_error" in op.meta:
            continue            # its own finding says why
        plan = ctx.setup_plan(op.setup)
        moves = plan.toolpath.moves[op.start:op.end] if plan.toolpath is not None else ()
        if any(int(kind) not in (RAPID, DWELL) for kind in (moves["kind"] if len(moves) else ())):
            continue
        named = bool(op.spec.faces) or op.spec.region is not None
        out.append(finding(
            "empty_operation", "error" if named else "warning", "empty_operation",
            f"operation {op.index + 1} ({op.summary}, setup {op.setup}) cuts nothing: its toolpath has no cutting move",
            "check the faces or region it names, its depth, and what the operations before it already took off; drop "
            "the operation if nothing is left to do",
            [{"setup": op.setup, "operation": op.index}]))
    return out
