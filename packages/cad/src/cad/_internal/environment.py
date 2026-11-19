"""Every environment variable cad reads, declared once.

A variable is read where it is used, by the name declared here; this table is the one list of them and says
what each is for and who sets it. A variable is added by adding its row first, and a policy test holds the
table, the source and the documentation together: a name the source reads and the table lacks fails, as does a
row nothing reads, a public row the server's README does not list, and a skill that names a variable that is
not public.

A variable exists only where nothing else can carry the value: it must be known before a process starts (a
folder, a port, a limit a daemon reads once), or it crosses from a process to the one it starts. A choice a
person makes once and keeps is a setting (``cad telemetry``, ``cad update auto``), an input of one call is that
call's option, and how a third-party tool is found is the integration's own business, never a variable: cad
runs the program its extra pins, and a person who wants another build runs it themselves on the files cad
writes.

The tiers:

- ``PUBLIC``: a person or an agent may set it. Listed in the server's README; the only tier a skill may name.
- ``DEVELOPMENT``: for a contributor, a test or an experiment. Never named to a person who only installed cad.
- ``INTERNAL``: set by cad's own processes for the processes they start. Never set by hand.
- ``DEPRECATED``: still honoured, and on its way out: named nowhere but here and in the note of its removal.

The standard library alone: the server and the library both read it.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass

__all__ = ["DEPRECATED", "DEVELOPMENT", "INTERNAL", "PUBLIC", "TIERS", "VARIABLES", "Variable", "deprecated",
           "named", "off", "table"]

PUBLIC, DEVELOPMENT, INTERNAL, DEPRECATED = "public", "development", "internal", "deprecated"
TIERS = (PUBLIC, DEVELOPMENT, INTERNAL, DEPRECATED)


@dataclass(frozen=True)
class Variable:
    """One environment variable: its name, who sets it (``tier``) and what it does, in a line. A deprecated
    one says what to do instead (``instead``)."""

    name: str
    tier: str
    summary: str
    instead: str = ""


def _table(*rows: Variable) -> dict[str, Variable]:
    table = {row.name: row for row in rows}
    assert len(table) == len(rows), "an environment variable is declared twice"
    return table


#: Every variable, by name. The order within a tier is the order the server's README lists them in.
VARIABLES: dict[str, Variable] = _table(
    # --- where cad keeps things ------------------------------------------------------------------------------
    Variable("CAD_STATE_DIR", PUBLIC, "the folder of the person's settings and the records of their documents"),
    Variable("CAD_CACHE_DIR", PUBLIC, "the folder of what cad can make again: built documents and the environments "
                                      "it installs"),
    Variable("CAD_ENGINE_DIR", PUBLIC, "the folder of the server's door and lock: one server runs per folder"),
    # --- the server ------------------------------------------------------------------------------------------
    Variable("CAD_ENGINE_PORT", PUBLIC, "the server's HTTP port (0: any free one); `cad server start --port` says "
                                        "the same for one start"),
    Variable("CAD_ENGINE_WORKERS", PUBLIC, "the most model workers alive at once (default: the machine's cores)"),
    Variable("CAD_ENGINE_WORKER_RSS_MB", PUBLIC, "the memory the server's kernel processes may hold together, in "
                                                 "MiB (default: a quarter of the machine's; 0: no cap)"),
    Variable("CAD_ENGINE_MEMORY_MB", PUBLIC, "the memory the server may hold documents in, in MiB (default: a "
                                             "quarter of the machine's)"),
    Variable("CAD_ENGINE_CHECKS", PUBLIC, "how many checks are measured at once (default: half the cores, one to "
                                          "four)"),
    Variable("CAD_ENGINE_CHECK_SECONDS", PUBLIC, "the longest one check may run before it is stopped (default: "
                                                 "half an hour; 0: no limit)"),
    Variable("CAD_ENGINE_CHECK_RSS_MB", PUBLIC, "the most memory one check may take, in MiB (default: the kernel "
                                                "processes' cap; 0: no limit)"),
    # --- what cad sends and fetches --------------------------------------------------------------------------
    Variable("CAD_TELEMETRY", PUBLIC, "0: no usage counts from this process; 1: on, over the person's saved "
                                      "choice. DO_NOT_TRACK=1 turns it off too"),
    Variable("CAD_UPDATE_CHECK", PUBLIC, "0: this server neither looks for a newer release nor installs one"),
    # --- integrations ----------------------------------------------------------------------------------------
    Variable("CAD_KICAD_3DMODELS", PUBLIC, "more folders a board's 3D models are read from, separated as PATH is"),
    Variable("CAD_KICAD_CLI", PUBLIC, "another `kicad-cli` to check, export and edit boards with, in place of the "
                                      "one `cad[kicad]` brings (KiCad 9 or newer; a nightly's to edit)"),
    Variable("CAD_CCX", PUBLIC, "another CalculiX `ccx` to solve studies with, in place of the one `cad[calculix]` "
                                "brings (2.20 or newer)"),

    # --- development: tests, experiments and a checkout --------------------------------------------------------
    Variable("CAD_ENGINE_DEFAULT_PORT", DEVELOPMENT, "the port a server takes where none is named, in place of 3245"),
    Variable("CAD_ENGINE_CACHE_IDLE", DEVELOPMENT, "the seconds a cached document may lie idle"),
    Variable("CAD_ENGINE_TEND_SECONDS", DEVELOPMENT, "how often the daemon tends itself"),
    Variable("CAD_ENGINE_STANDBY", DEVELOPMENT, "0: the daemon keeps no standby process"),
    Variable("CAD_ENGINE_MESH", DEVELOPMENT, "how parts are meshed: processes (the default) or inline"),
    Variable("CAD_ENGINE_MEMO", DEVELOPMENT, "0: no memo hit, so every kernel call of a run runs"),
    Variable("CAD_ENGINE_BODIES", DEVELOPMENT, "0: no body is replayed, so every model body of a run runs"),
    Variable("CAD_ENGINE_DETERMINISM", DEVELOPMENT, "0: build123d's shape de-duplication is left in its own order, "
                                                    "without cad's patches"),
    Variable("CAD_ENGINE_PRESSURE", DEVELOPMENT, "the memory-pressure signal as given (0 or 1), in place of the "
                                                 "system's"),
    Variable("CAD_ENGINE_UPDATE_INSTALLER", DEVELOPMENT, "a command run in place of the hosted install command "
                                                         "(empty: none)"),
    Variable("CAD_ENGINE_UPDATE_FIRST_SECONDS", DEVELOPMENT, "how long install mode waits for its first answer"),
    Variable("CAD_UPDATE_FIND_LINKS", DEVELOPMENT, "a folder of wheels an update installs from, in place of PyPI"),
    Variable("CAD_PYPI_URL", DEVELOPMENT, "another address for PyPI's JSON API"),
    Variable("CAD_API_URL", DEVELOPMENT, "another address for the version feed and the analytics receiver"),
    Variable("CAD_INSTALLATION_VERSION", DEVELOPMENT, "the name a development build runs as, in place of its "
                                                      "release"),
    Variable("CAD_LAUNCHER_DIR", DEVELOPMENT, "the folder the `cad` command of 0.10.0 to 0.11.11 is looked for in"),
    Variable("CAD_VIEWER_DIST", DEVELOPMENT, "the folder the viewer's client is served from (`cad viewer "
                                             "--dist` says the same)"),
    Variable("CAD_VIEWER_WARM", DEVELOPMENT, "0: `cad viewer` warms no kernel as it launches"),
    Variable("CAD_MCP_APP_DIR", DEVELOPMENT, "the folder the CAD app's page is served from"),
    Variable("CAD_MCP_PRESENTATION", DEVELOPMENT, "the presentation forced on any host: inline, tabs or text"),
    Variable("CAD_KICAD_REFILL", DEVELOPMENT, "0: a board's pours are drawn as saved and no KiCad is fetched to "
                                              "draw one"),
    Variable("CAD_FONT_GUARD", DEVELOPMENT, "0: the guard against a font folder scan is not installed"),
    Variable("CAD_TELEMETRY_NOTICE", DEVELOPMENT, "0: a launch whose output reaches nobody prints no telemetry "
                                                  "notice"),

    # --- internal: one of cad's processes telling the next ---------------------------------------------------------
    Variable("CAD_ENGINE_WORKER", INTERNAL, "marks a kernel process the server started"),
    Variable("CAD_ENGINE_DISPLAY", INTERNAL, "the X display the server draws on, for its render processes"),
    Variable("CAD_ENGINE_XAUTHORITY", INTERNAL, "that display's authority file"),
    Variable("CAD_RUN_WITH", INTERNAL, "how `cad run` named the program's packages, for the worker that builds it"),
    Variable("CAD_UPDATE_PREPARE", INTERNAL, "marks the preparing pass of an automatic update"),
    Variable("CAD_INSTALL_BY_CAD", INTERNAL, "marks an install command cad itself started"),
    Variable("CAD_INSTALL_REPORT", INTERNAL, "the file an install command cad started writes its outcome to"),
    Variable("CAD_INSTALL_UPDATE", INTERNAL, "tells an install command cad started that it runs as an update"),
    Variable("CAD_INSTALL_ATTEMPT", INTERNAL, "names the run of the install command a server began"),
    Variable("CAD_INSTALL_FAILED", INTERNAL, "tells cad that the install command it started is ending badly"),
    Variable("CADGEN_TELEMETRY", INTERNAL, "turns telemetry off in a 0.10.0 server cad stops on Windows"),
)

_SAID: set[str] = set()


def named(tier: str) -> tuple[Variable, ...]:
    """The variables of one tier, in the table's order."""
    return tuple(row for row in VARIABLES.values() if row.tier == tier)


def off(name: str) -> bool:
    """Whether the switch ``name`` is turned off: set to ``0``. A switch is on unless it says so."""
    return os.environ.get(name, "").strip() == "0"


def deprecated(name: str) -> str:
    """The value of the deprecated variable ``name``, "" when it is unset. A set one is said once a process, on
    stderr, with what to do instead: it still decides what it did."""
    value = os.environ.get(name, "").strip()
    if value and name not in _SAID:
        _SAID.add(name)
        row = VARIABLES[name]
        print(f"cad: {name} is deprecated and will stop being read: {row.instead}", file=sys.stderr)
    return value


def table() -> str:
    """The public variables as the Markdown table the server's README carries: ``python -m
    cad._internal.environment`` prints it."""
    lines = ["| Variable | What it sets |", "| --- | --- |"]
    lines += [f"| `{row.name}` | {row.summary[0].upper()}{row.summary[1:]} |" for row in named(PUBLIC)]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    sys.stdout.write(table())
