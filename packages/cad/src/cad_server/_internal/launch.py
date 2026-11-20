"""How cad is installed and run: the uv tool ``cad`` (``uv tool install --managed-python --python 3.14 cad``), which the
install command installs and cad's own update upgrades to PyPI's newest of its major (``uv tool install --upgrade
"cad>=X,<N"``, ``auto_update``), and ``uvx``
for a line that runs a release from uv's cache (a plugin's server line, ``uvx ... cad@<version> mcp``).
``--managed-python --python 3.14`` (``PYTHON``) makes the environment the same on every machine, whatever interpreter
a GUI app's PATH happens to find first, and ``--no-config`` keeps the user's own uv settings (an index, a cache
policy) from resolving a ``uvx`` line differently.

Error hints print these from here.
"""

from __future__ import annotations

# The Python line this release is made for and runs on: cad's own uv calls and the install scripts ask for it. The
# promised line, ``uv tool install cad``, asks for none, so the tool may run on any line ``requires-python`` admits:
# the floor, older, or a newer one than this. The environment every model and kernel process runs in (``base``) is
# made with the engine's own interpreter, but on a line newer than this one, where the kernel's wheels may not exist
# yet, on this line, a Python uv manages (``base.kernel_python``). An environment with an integration whose tool is
# built for another line alone is made on that line (``extras.on``: blender's bpy, 3.13), the library in it.
PYTHON = "3.14"
# A ``uvx`` line, up to the requirement it runs from (``analytics``: a command that runs an installation uvx made).
LAUNCHER = ("uvx", "--no-config", "--managed-python", "--python", PYTHON, "--from")
# The package and its command, as messages name them.
COMMAND = "cad"


def reinstall_command(version: str | None = None) -> str:
    """``uv tool install --reinstall ... cad==<version>``: uv's own reinstall of the uv tool ``cad`` at ``version`` (by
    default this one), which puts back what an installation lacks."""
    if version is None:
        from cad_server import __version__ as version
    return " ".join(("uv", "tool", "install", "--reinstall", "--managed-python", "--python", PYTHON,
                     f"{COMMAND}=={version}"))
