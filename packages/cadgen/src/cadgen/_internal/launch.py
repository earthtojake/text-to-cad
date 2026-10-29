"""How cadgen is run: installed by ONE ``uvx`` command, then run by the ``cadgen`` command it writes.

An agent app starts cadgen's MCP server with ``uvx`` and the exact requirement, outside any
sandbox. uv keeps one installation per requirement and reuses it, so the same command means the
same installation, which starts or attaches to the selected port's engine. ``--no-config`` keeps
the user's own uv settings (an index, a cache policy) from resolving it differently, and
``--managed-python --python 3.13`` makes the installation the first command creates the same on
every machine, whatever interpreter a GUI app's PATH happens to find first.

The skills cannot run ``uvx``: an agent's shell is often a sandbox, and uv writes its cache before
it starts. So that installation registers itself and writes the proxy, ``~/.local/bin/cadgen``
(``cadgen._internal.installations``), and every skill runs ``cadgen +<version> ...``, which runs
that version's installation (``cadgen._internal.proxy``): the same installation, so the server,
every thread and every skill command reach one engine, the selected port's. A skill names ``uvx`` once, as the
command that installs, registers and writes them (``cadgen doctor``) when they are missing.

Error hints and ``cadgen doctor`` print these from here; the plugin's server configs and the
skills carry the same strings, stamped by the release and held to these by a repository test.
"""

from __future__ import annotations

LAUNCHER = ("uvx", "--no-config", "--managed-python", "--python", "3.13", "--from")


def launch_command(tool: str = "cadgen", version: str | None = None) -> str:
    """``uvx ... --from cadgen==<version> <tool>``: run ``tool`` (``cadgen`` or ``python``)
    from this version's installation, installing it first if uv has none."""
    if version is None:
        from cadgen import __version__ as version
    return " ".join((*LAUNCHER, f"cadgen=={version}", tool))


def pinned(version: str | None = None) -> str:
    """``cadgen +<version>``: the command a skill runs this version by, through the proxy."""
    if version is None:
        from cadgen import __version__ as version
    return f"cadgen +{version}"
