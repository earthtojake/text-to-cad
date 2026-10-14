"""``unused_tool``: a tool the job lists that no operation runs (an info note).

It is not drawn, checked or posted, so a typo in an operation's ``tool`` that picked another tool shows here. From the
parallel cam build.
"""

from __future__ import annotations

from cadgen._internal.cam.checks.base import finding

__all__ = ["run"]


def run(ctx) -> list[dict]:
    used = {op.tool.id for op in ctx.ops if op.tool is not None}
    unused = [tool for tool in ctx.job.tools if tool.id not in used]
    if not unused:
        return []
    names = ", ".join(f"{tool.id} ({tool.plain})" for tool in unused)
    return [finding(
        "unused_tool", "info", "unused_tool",
        f"{'Tools' if len(unused) > 1 else 'Tool'} {names} {'are' if len(unused) > 1 else 'is'} listed but no "
        "operation runs " + ("them" if len(unused) > 1 else "it"),
        "a tool no operation names is not drawn, checked or posted; drop it from tools, or check each operation's "
        "tool is the one meant",
        [{"tool": tool.id} for tool in unused])]
