"""How the server is run: installed by ONE ``uvx`` command, then run by the ``cad`` command it writes.

The install command runs the server's ``cad setup`` with ``uvx`` and the exact requirement
(``cad-server==<version>``), and an agent app starts the CAD app's transport the same way
(``cad-mcp==<version>``, its ``cad-mcp``), outside any sandbox. uv keeps one installation per
requirement and reuses it, so the same command means the same installation. ``--no-config`` keeps the
user's own uv settings (an index, a cache policy) from resolving it differently, and ``--managed-python
--python 3.14`` (``PYTHON``) makes the installation the first command creates the same on every machine,
whatever interpreter a GUI app's PATH happens to find first.

The skills cannot run ``uvx``: an agent's shell is often a sandbox, and uv writes its cache before
it starts. So the installation registers itself and writes the proxy, ``~/.local/bin/cad``
(``cad_server._internal.installations``), and every skill runs ``cad ...``, which runs the current
installation (``cad_server._internal.proxy``): the same installation, so the server, every thread and
every skill command share one daemon. Where no installation is registered, the command says the
``uvx`` line that installs, registers and writes them (``cad doctor``).

Error hints and ``cad doctor`` print these from here; the plugin's server configs carry the same
strings, stamped by the release and held to these by a repository test.
"""

from __future__ import annotations

# The one Python line the server runs on: the installation uvx makes runs it, so the engine does, and the
# environment every model and kernel process runs in (``base``) is made with the engine's own
# interpreter. The plugin's server configs and the install scripts carry the same line as text.
PYTHON = "3.14"
LAUNCHER = ("uvx", "--no-config", "--managed-python", "--python", PYTHON, "--from")
# The server's distribution and its command; the CAD app's transport (the shim's) and its command.
SERVER, COMMAND = "cad-server", "cad"
SHIM, SHIM_COMMAND = "cad-mcp", "cad-mcp"


def launch_command(tool: str = COMMAND, version: str | None = None) -> str:
    """``uvx ... --from cad-server==<version> <tool>``: run ``tool`` (``cad`` or ``python``)
    from this version's installation, installing it first if uv has none."""
    if version is None:
        from cad_server import __version__ as version
    return " ".join((*LAUNCHER, f"{SERVER}=={version}", tool))


def mcp_command(version: str | None = None) -> list[str]:
    """``uvx ... --from cad-mcp==<version> cad-mcp``, as words: the CAD app's server the plugins and
    Claude Desktop's entry start."""
    if version is None:
        from cad_server import __version__ as version
    return [*LAUNCHER, f"{SHIM}=={version}", SHIM_COMMAND]

