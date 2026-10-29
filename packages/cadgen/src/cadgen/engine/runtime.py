"""The Python environment a model asks the shared engine to execute in, and what two processes meet by.

Executable paths stay lexical: resolving a venv's Python symlink would silently run its base
interpreter. Installed dependencies are captured once at worker startup for saved build reuse;
installing or upgrading them requires an explicit engine restart. Project Python source is
reloaded and keyed by the build loader, independently of the environment's identity.

A client, a project's worker and the engine meet by protocol, document format and native line
(``refusal``), never by release: a project of another cadgen release that meets the engine is served,
and told once (``nudge``).
"""
from __future__ import annotations

import functools
import hashlib
import importlib.metadata as metadata
import importlib.util
import json
import os
import platform
import re
import sys
from pathlib import Path
from typing import Any

STARTUP = ("PYTHONPATH", "PYTHONHOME", "PYTHONSAFEPATH", "PYTHONNOUSERSITE", "PYTHONUSERBASE", "PYTHONPLATLIBDIR")
_METADATA = ("METADATA", "RECORD", "direct_url.json")
_LEGACY_METADATA = ("PKG-INFO", "SOURCES.txt", "installed-files.txt", "requires.txt",
                    "entry_points.txt", "top_level.txt", "dependency_links.txt")


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _stamp(path: Path | str) -> list[Any]:
    path = Path(path)
    try:
        found = path.stat()
        content = hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return [str(path), None]
    return [str(path), found.st_dev, found.st_ino, content]


@functools.cache
def dependencies() -> str:
    """One process-local installation snapshot, taken before a worker imports its kernel.

    Only build-closure reuse needs this snapshot; client identity and requests never inspect
    package inventories. Install or upgrade dependencies, then restart the selected engine.
    """
    from cadgen.engine.previous import version

    rows = [["cadgen", version(), str(Path(__file__).resolve().parent.parent)]]
    seen = set()
    for dist in metadata.distributions():
        location = getattr(dist, "_path", None)
        if location is None:
            rows.append(["installation", str(dist.locate_file("")),
                         [[entry, dist.read_text(entry)] for entry in _METADATA]])
            continue
        path = Path(location).resolve()
        token = str(path)
        if token in seen:
            continue
        seen.add(token)
        inventory = _LEGACY_METADATA if token.endswith(".egg-info") else _METADATA
        installed = [_stamp(path)] if path.is_file() else [_stamp(path / entry) for entry in inventory]
        rows.append(["installation", token, installed])
    return digest(sorted(rows))


# The distributions that may provide this Python's OCP, asked in this order, and the one cadgen
# depends on (``pyproject.toml``): what a remedy names to install.
OCP_PROVIDERS = ("cadquery-ocp", "cadquery-ocp-novtk")
OCP_DISTRIBUTION = "cadquery-ocp-novtk"
# The command that installs text-to-cad on this device, and updates it -- its engine with it: what a
# remedy names when the engine is the older side. macOS and Linux run the first, Windows PowerShell the
# second. cadgen.updates names the same two (``INSTALL``, ``INSTALL_WINDOWS``), which the standalone
# engine does not import; test_updates holds them equal.
INSTALLS = ("curl -fsSL https://texttocad.dev/install.sh | sh", "irm https://www.texttocad.dev/install.ps1 | iex")
INSTALL = INSTALLS[1] if os.name == "nt" else INSTALLS[0]
# What an execution descriptor holds (``describe``). A request's may hold more -- a newer cadgen of
# the same protocol adds a field -- which is carried, never refused (``validate``).
DESCRIPTOR = frozenset({"python", "prefix", "root", "release", "checkout", "startup", "compatibility", "fingerprint"})


def ocp_line(version: Any) -> str | None:
    """An OCP distribution's version as its line, major.minor -- ``8.0`` of ``8.0.1.1.0`` -- what two
    processes' kernels share to exchange native bytes: patch levels interoperate. The whole version
    where it has no such form; None for none."""
    if not isinstance(version, str) or not version:
        return None
    found = re.match(r"([0-9]+)\.([0-9]+)", version)
    return f"{int(found[1])}.{int(found[2])}" if found else version


def compatibility() -> dict[str, Any]:
    """What this process meets another by, never its release: the wire protocol its engine, clients
    and workers speak (``daemon.PROTOCOL``), the document format it writes (``format``,
    ``previous.FORMAT``) and those it reads (``reads``, ``document_migrations.readable``), and its
    native line (``native``: the system, the architecture and the OCP line, ``_native``). A copy of
    its own to each caller, read once a process."""
    from cadgen.engine.daemon import PROTOCOL
    from cadgen.engine.document_migrations import readable
    from cadgen.engine.previous import FORMAT

    return {"protocol": PROTOCOL, "format": FORMAT, "reads": readable(), "native": dict(_native()[0])}


@functools.cache
def _native() -> tuple[dict[str, Any], str | None]:
    """This process's native line and the distribution that provides its OCP, found once: installed
    packages are not watched (an install takes effect when the engine and the calling process
    restart), and a worker's descriptor is fixed at its start."""
    ocp = found = None
    spec = importlib.util.find_spec("OCP")
    origin = Path(spec.origin).resolve() if spec is not None and spec.origin else None
    for provider in OCP_PROVIDERS:
        try:
            dist = metadata.distribution(provider)
            if origin == Path(dist.locate_file("OCP/__init__.py")).resolve():
                ocp, found = dist.version, provider
                break
        except metadata.PackageNotFoundError:
            pass
    return {"system": platform.system(), "arch": platform.machine(), "ocp_line": ocp_line(ocp)}, found


def identity() -> dict[str, Any]:
    """This process as its hello says it (``client.hello``) and an engine answers one: what it meets
    another by (``compatibility``) -- ``protocol``, the format it ``writes``, those it ``reads``, its
    ``native`` line -- and its ``release``, which is information only."""
    from cadgen.engine.previous import version

    found = compatibility()
    return {"protocol": found["protocol"], "release": version(), "writes": found["format"],
            "reads": found["reads"], "native": found["native"]}


def side(found: Any) -> dict[str, Any]:
    """A side as the rule reads it (``refusal``) -- a hello, an engine's answer, or an execution
    descriptor (``describe``) -- by ``protocol``, ``release``, ``writes``, ``reads`` and ``native``, each
    None where it does not say."""
    if not isinstance(found, dict):
        return dict.fromkeys(("protocol", "release", "writes", "reads", "native"))
    if isinstance(found.get("compatibility"), dict):
        meets = found["compatibility"]
        return {"protocol": meets.get("protocol"), "release": found.get("release"), "writes": meets.get("format"),
                "reads": meets.get("reads"), "native": meets.get("native")}
    return {key: found.get(key) for key in ("protocol", "release", "writes", "reads", "native")}


class Refusal(ValueError):
    """Why two sides do not meet (``refusal``, ``check_native``): ``what`` differs -- ``protocol``,
    ``format`` or ``native`` -- in ``words`` naming both sides, and the ``remedy`` that makes them meet,
    said as one line: ``<words>: <remedy>``."""

    def __init__(self, what: str, words: str, remedy: str) -> None:
        super().__init__(f"{words}: {remedy}")
        self.what, self.words, self.remedy = what, words, remedy


def _number(name: Any) -> int | None:
    """A document format's place among formats: 10 of ``xbf/10``; None for no format."""
    found = re.fullmatch(r"xbf/([0-9]+)", name) if isinstance(name, str) else None
    return int(found[1]) if found else None


def _span(reads: list[str]) -> str:
    """The formats a side reads, in words: ``xbf/8 to xbf/10``."""
    ordered = sorted(reads, key=lambda name: _number(name) or 0)
    return ordered[0] if len(ordered) == 1 else f"{ordered[0]} to {ordered[-1]}"


def _newer(name: Any, reads: list[str]) -> bool:
    """Whether format ``name`` is newer than every one of ``reads``: what only a newer reader reads."""
    at = _number(name)
    return at is not None and all((_number(read) or 0) < at for read in reads)


def _line_order(theirs: str, ours: str) -> int | None:
    """-1, 0 or 1 as OCP line ``theirs`` is older than, the same as or newer than ``ours``; None where
    either is no major.minor."""
    if not (re.fullmatch(r"[0-9]+\.[0-9]+", theirs) and re.fullmatch(r"[0-9]+\.[0-9]+", ours)):
        return None
    first, second = tuple(map(int, theirs.split("."))), tuple(map(int, ours.split(".")))
    return (first > second) - (first < second)


def _pin(line: str) -> str:
    """The requirement that installs OCP line ``line``: ``==8.0.*``."""
    return f"=={line}.*" if re.fullmatch(r"[0-9]+\.[0-9]+", line) else f"=={line}"


def _platform(native: dict[str, Any]) -> str:
    return f"{native.get('system')} {native.get('arch')}"


def refusal(peer: Any, engine: Any, *, port: int | None = None) -> Refusal | None:
    """Whether ``peer`` -- a client's hello, or the execution a project's worker runs in (``describe``)
    -- meets ``engine`` (its hello's answer, or its ``identity``): the same ``protocol``, a document
    format the engine reads (the peer's ``writes`` among its ``reads``), and the same native line (the
    system, the architecture and the OCP major.minor). None when it does; else why not (``Refusal``),
    naming both sides and the remedy, ``port`` the engine's. The release never decides: a release apart
    is told once, as a nudge (``nudge``)."""
    peer, engine = side(peer), side(engine)
    at = "its port" if port is None else f"port {port}"
    theirs, ours = peer["release"], engine["release"]
    if peer["protocol"] != engine["protocol"] or type(peer["protocol"]) is not int:
        spoken = peer["protocol"] if type(peer["protocol"]) is int else "no protocol it names"
        return Refusal("protocol", f"cadgen client speaks protocol {spoken}, the engine on {at} protocol "
                                   f"{engine['protocol']}",
                       f"update the older one (run `{INSTALL}` for the engine; `uv pip install -U cadgen` in the project)")
    reads = engine["reads"] if isinstance(engine["reads"], list) and engine["reads"] else None
    engine_named = f"the engine (cadgen {ours}, {at})"
    if reads is None:
        return Refusal("format", f"this project's cadgen {theirs} writes {peer['writes']}; {engine_named} does "
                                 "not say which formats it reads", f"update the engine: run `{INSTALL}`")
    if peer["writes"] not in reads:
        if _newer(peer["writes"], reads):
            return Refusal("format", f"this project's cadgen {theirs} writes {peer['writes']}; {engine_named} reads "
                                     f"up to {_span(reads).rpartition(' to ')[2]}", f"update the engine: run `{INSTALL}`")
        writes = peer["writes"] if _number(peer["writes"]) is not None else "no format it names"
        return Refusal("format", f"this project's cadgen {theirs} writes {writes}; {engine_named} reads {_span(reads)}",
                       "update the project's cadgen: uv pip install -U cadgen in the project environment")
    native = peer["native"] if isinstance(peer["native"], dict) else {}
    own = engine["native"] if isinstance(engine["native"], dict) else {}
    if all(native.get(key) == own.get(key) for key in ("system", "arch", "ocp_line")):
        return None
    if (native.get("system"), native.get("arch")) != (own.get("system"), own.get("arch")):
        return Refusal("native", f"the project's Python runs on {_platform(native)}; the engine on {_platform(own)}",
                       f"use a {_platform(own)} Python for the project")
    line, wanted = native.get("ocp_line"), own.get("ocp_line")
    providers = " or ".join(OCP_PROVIDERS)
    if wanted is None:
        return Refusal("native", f"the project's Python has OCP {line} ({_platform(native)}); the engine has no OCP "
                                 f"from {providers}", f"update the engine: run `{INSTALL}`")
    install = f"install {OCP_DISTRIBUTION}{_pin(wanted)} in the project environment"
    if line is None:
        return Refusal("native", f"the project's Python has no OCP from {providers} ({_platform(native)}); the "
                                 f"engine has OCP {wanted}", install)
    order = _line_order(line, wanted)
    if order == -1:
        return Refusal("native", f"the project's Python has the older OCP {line} ({_platform(native)}); the engine "
                                 f"has OCP {wanted}", install)
    older = "the older " if order == 1 else ""
    return Refusal("native", f"the project's Python has OCP {line} ({_platform(native)}); the engine has {older}OCP "
                             f"{wanted}", f"{install}, or update the engine")


def nudge(project: Any, engine: Any) -> str | None:
    """The one line a project of another release that meets the engine (``refusal``) is told at its
    worker's start, never a refusal (``daemon.Worker``): an older project to update cadgen in its
    environment, a newer one to update the engine. None for the same release, or one either side
    cannot order (``daemon.rank``)."""
    from cadgen.engine.daemon import rank

    theirs, ours = rank(project), rank(engine)
    if theirs is None or ours is None or theirs == ours:
        return None
    if theirs < ours:
        return f"project cadgen {project} is older than the engine's {engine}: uv pip install -U cadgen in the project environment"
    return f"the engine runs cadgen {engine}, this project {project}: run `{INSTALL}` to update the engine"


def check_native(found: Any) -> None:
    """Refuse native bytes before reading them -- a document a peer wrote (``found``, its
    ``compatibility``) is read here only in a format this process reads and on its native line --
    and refuse them as well when the kernel this process has loaded is of another line than its
    installation's (a reinstall under a running process)."""
    from cadgen.engine.previous import version

    ours = compatibility()
    theirs = found if isinstance(found, dict) else {}
    if theirs.get("format") not in ours["reads"]:
        written = theirs.get("format") if _number(theirs.get("format")) is not None else "no format it names"
        remedy = ("update cadgen here: uv pip install -U cadgen in this environment" if _newer(written, ours["reads"])
                  else "build it again with this cadgen")
        raise Refusal("format", f"the document is {written}, which this Python's cadgen {version()} does not read "
                                f"(it reads {_span(ours['reads'])})", remedy)
    native = theirs.get("native") if isinstance(theirs.get("native"), dict) else {}
    own = ours["native"]
    if (native.get("system"), native.get("arch")) != (own["system"], own["arch"]):
        raise Refusal("native", f"the document was made on {_platform(native)}; this Python runs on {_platform(own)}",
                      f"use a {_platform(native)} Python here")
    if native.get("ocp_line") != own["ocp_line"]:
        line = native.get("ocp_line")
        if not isinstance(line, str):
            raise Refusal("native", f"the document names no OCP line; this Python has OCP {own['ocp_line']}",
                          "build it again with this cadgen")
        raise Refusal("native", f"the document's kernel is OCP {line} ({_platform(native)}); this Python has OCP "
                                f"{own['ocp_line']}", f"install {_native()[1] or OCP_DISTRIBUTION}{_pin(line)} in this environment")
    loaded = sys.modules.get("OCP")
    if loaded is not None and ocp_line(getattr(loaded, "__version__", None)) != own["ocp_line"]:
        raise ValueError("the imported native kernel differs from the installed OCP distribution")


def describe(environment: dict[str, str] | None = None) -> dict[str, Any]:
    from cadgen.engine.previous import version

    env = os.environ if environment is None else environment
    path = env.get("PYTHONPATH")
    startup = {name: env.get(name, "") for name in STARTUP}
    if path:  # an empty one is no path, as Python reads it; an empty entry in a longer one is the folder
        startup["PYTHONPATH"] = os.pathsep.join(os.path.abspath(item or os.curdir) for item in path.split(os.pathsep))
    found = {"python": os.path.abspath(sys.executable), "prefix": os.path.abspath(sys.prefix),
             "root": str(Path(__file__).resolve().parents[2]), "release": version(),
             "checkout": (Path(__file__).resolve().parents[3] / "pyproject.toml").is_file(),
             "startup": startup, "compatibility": compatibility()}
    found["fingerprint"] = digest(found)
    return found


def validate(found: Any, *, server: bool = True, port: int | None = None) -> dict[str, Any]:
    """An execution descriptor (``describe``) a request names, checked before anything runs in it: its
    fields (one more, a newer cadgen's of the same protocol, is carried, never refused), its absolute
    paths, its fingerprint and, asked of the side that runs it (``server``), that it meets this process
    (``refusal``: protocol, document format and native line, ``port`` this engine's). Its release is
    information: a project of another release that meets the engine is served."""
    if not isinstance(found, dict) or not DESCRIPTOR <= found.keys():
        raise ValueError("a build requires its Python execution environment")
    if any(not isinstance(found[name], str) or not os.path.isabs(found[name]) for name in ("python", "prefix", "root")):
        raise ValueError("the model's Python, prefix and cadgen import root must be absolute paths")
    if not isinstance(found["release"], str) or not isinstance(found["compatibility"], dict):
        raise ValueError("a build requires its Python execution environment")
    if found["fingerprint"] != digest({name: value for name, value in found.items() if name != "fingerprint"}):
        raise ValueError("the model's Python execution fingerprint is invalid")
    if server:
        refused = refusal(found, identity(), port=_selected() if port is None else port)
        if refused is not None:
            raise refused
    return found


def _selected() -> int | None:
    """This process's selected port (``daemon.selected_port``) for a refusal's words; None for none."""
    from cadgen.engine.daemon import selected_port

    try:
        return selected_port()
    except ValueError:
        return None


def key(script: str, execution: dict[str, Any] | None) -> str:
    """One slot per script/interpreter; the pool replaces changed startup environments."""
    interpreter = {name: execution[name] for name in ("python", "prefix", "root")} if execution is not None else None
    return os.path.normcase(script) + ("::" + digest(interpreter) if interpreter is not None else "")



def closure() -> dict[str, Any]:
    """The worker's startup snapshot, also captured once for explicit offline builds."""
    return {"dependencies": dependencies(), "python": platform.python_version()}
