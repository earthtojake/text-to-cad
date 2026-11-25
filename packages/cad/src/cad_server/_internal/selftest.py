"""A release's own check of itself, run once before cad's update lets an environment run it.

cad's update builds a newer release in a folder of its own and runs this module there as ``__main__``
(``cad_server._internal.store.verify``), by the environment's interpreter with nothing on its import path but the
standard library and that folder: the way every process of the environment will run it. It imports what the ``cad``
command, the server and the stdio transport import -- so a package the build lacks, or one built for another
interpreter or computer, fails here and not in a person's command -- and says ``cad <release>`` as its last line.
Exit status 0 only where all of it loaded. It starts nothing, reads no folder of the person's and writes nothing but
Python's own bytecode beside the modules it imports, which the first commands then find compiled.

Every release from the first with a store has this module under this name, run this way: the release that checks is
the one being left, and it knows nothing of the one it checks but this.
"""

from __future__ import annotations

# What a release imports to run: the command line, the server's daemon with the application it hosts, the stdio
# transport an agent app starts, and the packages their work loads as it comes (the mesh formats' numpy, the DXF
# pane's ezdxf, the previews' Pillow), each with its compiled parts.
MODULES = ("cad_server.cli", "cad_server.cli.server", "cad_server.cli.update", "cad_server.cli.doctor",
           "cad_server.engine.daemon", "cad_server._internal.engine_host", "cad_server._internal.auto_update",
           "cad_server._internal.auto_update_helper", "cad_server._internal.store", "cad_mcp.shim",
           "numpy", "ezdxf", "PIL.Image")


def main() -> int:
    import importlib

    for name in MODULES:
        importlib.import_module(name)
    import cad_server

    print(f"cad {cad_server.__version__}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
