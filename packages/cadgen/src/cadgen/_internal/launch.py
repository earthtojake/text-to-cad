"""The one command that runs cadgen: ``uvx`` with the exact requirement, the CAD plugin's way.

An agent app starts cadgen's MCP server with it, and every skill tells the agent to run its
commands with it. uv keeps one installation per requirement and reuses it, so the same command
means the same installation -- and cadgen names its warm daemon after the installation's folder,
so the server, every thread and every skill command share one daemon. ``--no-config`` keeps the
user's own uv settings (an index, a cache policy) from resolving it differently, and
``--managed-python --python 3.13`` makes the installation the first command creates the same on
every machine, whatever interpreter a GUI app's PATH happens to find first.

Error hints and ``cadgen doctor`` print it from here; the plugin's server configs and the skills
carry the same string, stamped by the release and held to this one by a repository test.
"""

from __future__ import annotations

LAUNCHER = ("uvx", "--no-config", "--managed-python", "--python", "3.13", "--from")


def launch_command(tool: str = "cadgen", version: str | None = None) -> str:
    """``uvx ... --from cadgen==<version> <tool>``: run ``tool`` (``cadgen`` or ``python``)
    from this version's installation."""
    if version is None:
        from cadgen import __version__ as version
    return " ".join((*LAUNCHER, f"cadgen=={version}", tool))
