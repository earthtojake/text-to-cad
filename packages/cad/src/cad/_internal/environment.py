"""Every environment variable cad reads, declared once.

A variable is read where it is used, by the name declared here; this table is the one list of them and says
what each is for and who sets it. A variable is added by adding its row first, and a policy test holds the
table, the source and the documentation together: a name the source reads and the table lacks fails, as does a
row nothing reads, a public row the server's README does not list, and a skill that names a variable that is
not public.

A variable exists only where nothing else can carry the value: it must be known before a process starts (a
folder, a port, a limit a daemon reads once), or it crosses from a process to the one it starts. A choice a
person makes once and keeps is a setting (``cad telemetry``, ``cad update auto``), an input of one call is that
call's option. cad runs the program an integration's extra pins: a variable names another copy only as the last
resort, where the pinned one does not run on a person's computer (``CAD_KICAD_CLI``, ``CAD_CCX``).

A public variable that is configuration a person keeps -- the server's limits and port, how an integration finds
what it reads or runs -- is also a saved setting (``setting=True``), which the variable overrides: the variable is
for one process (a test, a shell, a launcher), the setting for every process on the computer, whoever starts it.
The one declaration gives both: the setting's key, derived from the name (``key``: ``CAD_ENGINE_WORKERS`` is
``engine_workers``), what values it takes (``kind``, checked before one is saved), whether the server reads it only
as it starts (``at_start``), the ``cad config`` command that shows and changes it, and its column in the server's
README. Every read of such a variable goes through ``value``: the environment's value where it is set and not
blank, else the saved one, else ``""`` (the reader's own default). Saved values are the ``config`` section of the
person's ``settings.json`` in the state folder, ``{key: "value as typed"}``, which this module only reads, and never
fails to: a file that is missing, unreadable or malformed holds no saved value. The server writes it
(``cad_server.settings``). The other public variables are no setting: three say where the settings and the server
are, and two already override a choice with a command of its own (``cad telemetry``, ``cad update auto``).

The tiers:

- ``PUBLIC``: a person or an agent may set it. Listed in the server's README; the only tier a skill may name.
- ``DEVELOPMENT``: for a contributor, a test or an experiment. Never named to a person who only installed cad.
- ``INTERNAL``: set by cad's own processes for the processes they start. Never set by hand.
- ``DEPRECATED``: still honoured, and on its way out: named nowhere but here and in the note of its removal.

The standard library alone: the server and the library both read it.
"""

from __future__ import annotations

import math
import os
import re
import sys
from dataclasses import dataclass

__all__ = ["DEFAULT", "DEPRECATED", "DEVELOPMENT", "ENVIRONMENT", "INTERNAL", "KINDS", "PUBLIC", "SAVED", "SECTION",
           "SOURCES", "TIERS", "VARIABLES", "Variable", "check", "deprecated", "named", "off", "resolved", "saved",
           "setting", "settings", "table", "value"]

PUBLIC, DEVELOPMENT, INTERNAL, DEPRECATED = "public", "development", "internal", "deprecated"
TIERS = (PUBLIC, DEVELOPMENT, INTERNAL, DEPRECATED)
#: Where a value in effect came from (``resolved``), and the section of ``settings.json`` the saved values are kept
#: in: the engine's own words (``cad.engine.places``), which its modules read a setting by.
ENVIRONMENT, SAVED, DEFAULT = "environment", "saved", "default"
SOURCES = (ENVIRONMENT, SAVED, DEFAULT)
SECTION = "config"
#: The values a setting takes, by its kind, as ``check`` says them when it refuses one.
KINDS = {
    "count": "a whole number of zero or more",
    "number": "a number of zero or more",
    "port": "a port, a whole number from 0 to 65535",
    "file": "the full path of a file",
    "folders": "full paths of folders, separated as PATH is",
    "switch": "0 (off) or 1 (on)",
}


@dataclass(frozen=True)
class Variable:
    """One environment variable: its name, who sets it (``tier``) and what it does, in a line. A deprecated
    one says what to do instead (``instead``). A public one that is configuration a person keeps is also a saved
    setting (``setting``), whose values are of a ``kind`` (``KINDS``), and which the server may read only as it
    starts (``at_start``), so a running one keeps the value it started with."""

    name: str
    tier: str
    summary: str
    instead: str = ""
    setting: bool = False
    kind: str = ""
    at_start: bool = False

    def __post_init__(self) -> None:
        assert not self.setting or (self.tier == PUBLIC and self.kind in KINDS), \
            f"{self.name}: a setting is a public variable of a declared kind"
        assert self.setting or not (self.kind or self.at_start), f"{self.name}: a kind is a setting's"

    @property
    def key(self) -> str:
        """The setting's key, from the variable's name by the one rule: without ``CAD_``, in lower case; "" for a
        variable that is no setting."""
        return self.name.removeprefix("CAD_").lower() if self.setting else ""  # places.setting_key's rule


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
                                        "the same for one start",
             setting=True, kind="port", at_start=True),
    Variable("CAD_ENGINE_WORKERS", PUBLIC, "the most model workers alive at once (default: the machine's cores)",
             setting=True, kind="count", at_start=True),
    Variable("CAD_ENGINE_WORKER_RSS_MB", PUBLIC, "the memory the server's kernel processes may hold together, in "
                                                 "MiB (default: a quarter of the machine's; 0: no cap)",
             setting=True, kind="number", at_start=True),
    Variable("CAD_ENGINE_WORKER_CEILING_MB", PUBLIC, "the most memory one busy kernel process may hold before the "
                                                     "server stops it, in MiB (default: half the machine's; 0: none)",
             setting=True, kind="number", at_start=True),
    Variable("CAD_ENGINE_MEMORY_MB", PUBLIC, "the memory the server may hold documents in, in MiB (default: a "
                                             "quarter of the machine's)",
             setting=True, kind="number", at_start=True),
    Variable("CAD_ENGINE_CHECKS", PUBLIC, "how many checks are measured at once (default: half the cores, one to "
                                          "four)",
             setting=True, kind="count", at_start=True),
    Variable("CAD_ENGINE_CHECK_SECONDS", PUBLIC, "the longest one check may run before it is stopped (default: "
                                                 "half an hour; 0: no limit)",
             setting=True, kind="number", at_start=True),
    Variable("CAD_ENGINE_CHECK_RSS_MB", PUBLIC, "the most memory one check may take, in MiB (default: the kernel "
                                                "processes' cap; 0: no limit)",
             setting=True, kind="number", at_start=True),
    # --- what cad sends and fetches --------------------------------------------------------------------------
    Variable("CAD_TELEMETRY", PUBLIC, "0: no usage counts from this process; 1: on, over the person's saved "
                                      "choice. DO_NOT_TRACK=1 turns it off too"),
    Variable("CAD_UPDATE_CHECK", PUBLIC, "0: this server neither looks for a newer release nor installs one"),
    # --- integrations ----------------------------------------------------------------------------------------
    Variable("CAD_KICAD_3DMODELS", PUBLIC, "more folders a board's 3D models are read from, separated as PATH is",
             setting=True, kind="folders"),
    Variable("CAD_KICAD_REFILL", PUBLIC, "0: a board's copper pours are drawn as its file saved them, and no KiCad "
                                         "is fetched to show a board (default: KiCad refills them on a copy first)",
             setting=True, kind="switch"),
    Variable("CAD_KICAD_CLI", PUBLIC, "another `kicad-cli` to check, export and edit boards with, in place of the "
                                      "one `cad[kicad]` brings (KiCad 9 or newer; a nightly's to edit)",
             setting=True, kind="file"),
    Variable("CAD_CCX", PUBLIC, "another CalculiX `ccx` to solve studies with, in place of the one `cad[calculix]` "
                                "brings (2.20 or newer)",
             setting=True, kind="file"),

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
    Variable("CAD_ENGINE_UPDATE_INSTALLER", DEVELOPMENT, "a command the bridge runs in place of the hosted install "
                                                         "command (empty: none, and the server runs nothing by "
                                                         "itself)"),
    Variable("CAD_ENGINE_UPDATE_FIRST_SECONDS", DEVELOPMENT, "how long install mode waits for its first answer"),
    Variable("CAD_UPDATE_FIND_LINKS", DEVELOPMENT, "a folder of wheels an update installs from, in place of PyPI"),
    Variable("CAD_PYPI_URL", DEVELOPMENT, "another address for PyPI's JSON API"),
    Variable("CAD_API_URL", DEVELOPMENT, "another address for the version feed and the analytics receiver"),
    Variable("CAD_INSTALLATION_VERSION", DEVELOPMENT, "the name a development build runs as, in place of its "
                                                      "release"),
    Variable("CAD_INSTALL_PATH_ONLY", DEVELOPMENT, "1: the agent apps' commands are looked for on PATH and in "
                                                   "~/.local/bin alone, never in Homebrew's or npm's folders"),
    Variable("CAD_LAUNCHER_DIR", DEVELOPMENT, "the folder the `cad` command of 0.10.0 to 0.11.11 is looked for in"),
    Variable("CAD_VIEWER_DIST", DEVELOPMENT, "the folder the viewer's client is served from (`cad viewer "
                                             "--dist` says the same)"),
    Variable("CAD_VIEWER_WARM", DEVELOPMENT, "0: `cad viewer` warms no kernel as it launches"),
    Variable("CAD_MCP_APP_DIR", DEVELOPMENT, "the folder the CAD app's page is served from"),
    Variable("CAD_MCP_PRESENTATION", DEVELOPMENT, "the presentation forced on any host: inline, tabs or text"),
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
    Variable("CAD_INSTALL_ATTEMPT", INTERNAL, "the name 0.11.12 and 0.11.13 give their server's run: never read, "
                                              "and taken out of every cad command the install command starts"),
    Variable("CAD_INSTALL_FAILED", INTERNAL, "tells cad, at the install command's last step, that its run in the agent "
                                             "apps went badly, so no release is kept as done"),
    Variable("CAD_PLUGIN_SERVER_RUN", INTERNAL, "names the run in the agent apps that this release's server began"),
    Variable("CAD_PLUGIN_BY", INTERNAL, "who began a run in the agent apps (`script`: the install command)"),
    Variable("CAD_PLUGIN_REPORT", INTERNAL, "the file a run in the agent apps writes each app's status to, for the "
                                            "install command"),
    Variable("CADGEN_TELEMETRY", INTERNAL, "turns telemetry off in a 0.10.0 server cad stops on Windows"),
)

_SAID: set[str] = set()


def named(tier: str) -> tuple[Variable, ...]:
    """The variables of one tier, in the table's order."""
    return tuple(row for row in VARIABLES.values() if row.tier == tier)


def settings() -> tuple[Variable, ...]:
    """The variables that are also saved settings, in the table's order."""
    return tuple(row for row in VARIABLES.values() if row.setting)


def setting(word: str) -> Variable | None:
    """The setting ``word`` names, by its key (``engine_workers``) or its variable's name (``CAD_ENGINE_WORKERS``);
    None for a word that names none."""
    for row in settings():
        if word in (row.key, row.name):
            return row
    return None


def check(row: Variable, text: str) -> str:
    """``text`` as a value of the setting ``row``, unchanged, or ``ValueError`` saying what its kind takes: checked
    before a value is saved, so a saved one is never what the variable's reader would take for unset or refuse."""
    given = text.strip()
    ok = bool(given)
    if ok and row.kind in ("count", "port"):
        ok = re.fullmatch(r"\d+", given) is not None and (row.kind == "count" or int(given) <= 65535)
    elif ok and row.kind == "number":
        try:
            number = float(given)
        except ValueError:
            ok = False
        else:
            ok = math.isfinite(number) and number >= 0
    elif ok and row.kind == "file":
        ok = os.path.isabs(os.path.expanduser(given))
    elif ok and row.kind == "folders":
        parts = [part for part in given.split(os.pathsep) if part.strip()]
        ok = bool(parts) and all(os.path.isabs(os.path.expanduser(part.strip())) for part in parts)
    elif ok and row.kind == "switch":
        ok = given in ("0", "1")
    if not ok:
        raise ValueError(f"{row.key} takes {KINDS[row.kind]}, not {text!r}")
    return text


def saved() -> dict[str, str]:
    """The saved settings, by key (``cad.engine.places.saved_settings``, which never raises: a file it cannot read
    saves nothing)."""
    from cad.engine.places import saved_settings

    return saved_settings()


def resolved(name: str) -> tuple[str, str]:
    """The value of the variable ``name`` in effect and where it came from (``SOURCES``): the environment's where it
    is set and not blank, as it is set; else, for a setting, the saved value where one is; else ``""``, which its
    reader takes for its own default. Only a setting consults the saved file (``cad.engine.places.setting``, which
    the engine's own modules read by)."""
    if VARIABLES[name].setting:
        from cad.engine.places import setting as in_effect

        return in_effect(name)
    given = os.environ.get(name, "")
    return (given, ENVIRONMENT) if given.strip() else ("", DEFAULT)


def value(name: str) -> str:
    """The value of the variable ``name`` in effect (``resolved``): every read of a setting's variable is this."""
    return resolved(name)[0]


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
    """The public variables as the Markdown table the server's README carries, each with its setting's key where it
    is one: ``python -m cad._internal.environment`` prints it."""
    lines = ["| Variable | Setting | What it sets |", "| --- | --- | --- |"]
    lines += [f"| `{row.name}` | {f'`{row.key}`' if row.setting else ''} | {row.summary[0].upper()}{row.summary[1:]} |"
              for row in named(PUBLIC)]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    sys.stdout.write(table())
