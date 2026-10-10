"""Autorouting with Freerouting: finding it, running it, and keeping what it routed.

Freerouting (https://github.com/freerouting/freerouting, GPL-3.0) is the
open-source autorouter KiCad users run. cadgen runs it as a separate program
and never ships or imports it. It is found, in this order:

1. ``CADGEN_FREEROUTING``: a Freerouting jar, its launcher (``freerouting``,
   ``freerouting.exe``) or the folder that holds one (``freerouting.app`` on
   macOS, the unzipped Linux release);
2. ``freerouting`` on ``PATH``;
3. where Freerouting's own installers put it: ``freerouting.app`` in
   ``/Applications`` or ``~/Applications`` on macOS,
   ``%LOCALAPPDATA%\\freerouting`` or ``Program Files\\freerouting`` on Windows,
   ``/opt/freerouting`` on Linux.

Freerouting's installers and its Linux zip carry their own Java runtime. A jar
needs Java :data:`JAVA_MAJOR` or newer: ``CADGEN_JAVA``, else ``JAVA_HOME``,
else ``java`` on ``PATH``, else where Java's installers put it (Homebrew's
keg-only ``openjdk`` and ``/usr/libexec/java_home`` on macOS, ``/usr/lib/jvm``
on Linux, Eclipse Adoptium's and Microsoft's builds on Windows).

A run is isolated as a ``kicad-cli`` run is: its files are staged in a
temporary folder, Freerouting's settings and log go to a folder of the run's
own (``--user_data_path``), its ``FREEROUTING__*`` environment overrides are
dropped, its window never opens, its analytics are off (``-da``) and it never
reaches the network (see :data:`_OFFLINE_JAVA`). It routes
single-threaded for at most the requested passes, so the same board always
routes the same way; a run that outlives its timeout is stopped and fails the
build, rather than leaving a route that depends on how fast the machine was.
"""

from __future__ import annotations

import functools
import glob
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

import cadgen
from cadgen.kicad.design import Board, DesignError, Net, kicad_net_name
from cadgen.kicad.specctra import Routes, SessionError, board_dsn, read_session, with_routes

__all__ = [
    "FREEROUTING_MINIMUM",
    "JAVA_MAJOR",
    "Freerouting",
    "FreeroutingMissingError",
    "RouteError",
    "Routed",
    "find_freerouting",
    "freerouting_hint",
    "route_board",
    "run_freerouting",
]

#: The Java release Freerouting's jar is built for (its class files are Java 25's).
JAVA_MAJOR = 25
#: The oldest Freerouting whose command line and behaviour cadgen relies on.
FREEROUTING_MINIMUM = (2, 4, 0)
_RELEASES = "https://github.com/freerouting/freerouting/releases"
_TAIL_LINES = 12


class FreeroutingMissingError(RuntimeError):
    """No usable Freerouting, or no Java new enough for its jar. The message says what to do."""


class RouteError(RuntimeError):
    """Freerouting ran and failed, or answered with something cadgen cannot use."""


def freerouting_hint() -> str:
    """How to get Freerouting on this platform, as one sentence a person can act on."""
    if sys.platform == "darwin":
        return (
            f"download freerouting-<version>-macos-arm64.dmg from {_RELEASES} and drag freerouting.app into "
            "Applications (it carries its own Java); on an Intel Mac, download the .jar, install Java "
            f"{JAVA_MAJOR} (`brew install openjdk`) and set CADGEN_FREEROUTING to the jar"
        )
    if sys.platform.startswith("win"):
        return (
            f"install freerouting-<version>-windows-x64.msi from {_RELEASES} (it carries its own Java), "
            f"or set CADGEN_FREEROUTING to the release's .jar with Java {JAVA_MAJOR} installed (https://adoptium.net)"
        )
    return (
        f"unzip freerouting-<version>-linux-x64.zip from {_RELEASES} and set CADGEN_FREEROUTING to its "
        f"bin/freerouting (it carries its own Java), or set CADGEN_FREEROUTING to the release's .jar with "
        f"Java {JAVA_MAJOR} installed (Ubuntu: `sudo apt install openjdk-{JAVA_MAJOR}-jre-headless`; "
        "others: https://adoptium.net)"
    )


# --- Java ----------------------------------------------------------------------------------


def _java_major(version: str) -> int:
    parts = re.findall(r"\d+", version)
    if not parts:
        return 0
    major = int(parts[0])
    # Java 8 and older call themselves 1.x.
    return int(parts[1]) if major == 1 and len(parts) > 1 else major


@functools.lru_cache(maxsize=16)
def _java_version(java: str, stamp: tuple[int, int]) -> str | None:
    del stamp  # part of the cache key: a replaced java is asked again
    try:
        completed = subprocess.run([java, "-version"], capture_output=True, text=True, timeout=60, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    match = re.search(r'version "([^"]+)"', (completed.stderr or "") + (completed.stdout or ""))
    return match.group(1) if completed.returncode == 0 and match else None


def _executable(name: str) -> str:
    return f"{name}.exe" if sys.platform.startswith("win") else name


def _java_candidates() -> list[Path]:
    explicit = os.environ.get("CADGEN_JAVA", "").strip()
    if explicit:
        return [Path(explicit).expanduser()]
    found: list[Path] = []
    home = os.environ.get("JAVA_HOME", "").strip()
    if home:
        found.append(Path(home).expanduser() / "bin" / _executable("java"))
    on_path = shutil.which("java")
    if on_path:
        found.append(Path(on_path))
    if sys.platform == "darwin":
        found.extend(Path(prefix) / "opt" / "openjdk" / "bin" / "java" for prefix in ("/opt/homebrew", "/usr/local"))
        try:
            completed = subprocess.run(
                ["/usr/libexec/java_home", "-v", f"{JAVA_MAJOR}+"], capture_output=True, text=True, timeout=30, check=False
            )
            if completed.returncode == 0 and completed.stdout.strip():
                found.append(Path(completed.stdout.strip()) / "bin" / "java")
        except (OSError, subprocess.SubprocessError):
            pass
    elif sys.platform.startswith("win"):
        program_files = os.environ.get("ProgramFiles", r"C:\Program Files")
        for vendor in ("Eclipse Adoptium", "Microsoft", "Java", "Zulu", "Amazon Corretto"):
            found.extend(Path(path) for path in sorted(glob.glob(os.path.join(program_files, vendor, "*", "bin", "java.exe")), reverse=True))
    else:
        found.extend(Path(path) for path in sorted(glob.glob("/usr/lib/jvm/*/bin/java"), reverse=True))
    unique: list[Path] = []
    for path in found:
        if path not in unique:
            unique.append(path)
    return unique


def _find_java() -> tuple[Path, str]:
    too_old: list[str] = []
    for candidate in _java_candidates():
        try:
            stat = candidate.stat()
        except OSError:
            continue
        version = _java_version(str(candidate), (stat.st_mtime_ns, stat.st_size))
        if version is None:
            continue
        if _java_major(version) < JAVA_MAJOR:
            too_old.append(f"{candidate} is Java {version}")
            continue
        return candidate, version
    where = f" ({'; '.join(too_old)})" if too_old else ""
    raise FreeroutingMissingError(
        f"Freerouting's jar needs Java {JAVA_MAJOR} or newer, and none was found{where}: install Java "
        f"{JAVA_MAJOR} (macOS: `brew install openjdk`; Ubuntu: `sudo apt install openjdk-{JAVA_MAJOR}-jre-headless`; "
        "anywhere: https://adoptium.net) and set CADGEN_JAVA or JAVA_HOME if it is not on PATH, or use a "
        f"Freerouting installer that carries its own Java ({freerouting_hint()})"
    )


# --- Freerouting ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Freerouting:
    """How to run Freerouting: its own launcher, or its jar and the Java to run it."""

    command: tuple[str, ...]
    location: Path
    java_version: str | None = None


def _launcher(path: Path) -> Path:
    """The executable a Freerouting install folder holds (a macOS app, the Linux zip, a Windows install), else ``path``."""
    if not path.is_dir():
        return path
    for inner in (
        path / "Contents" / "MacOS" / "freerouting",
        path / "bin" / "freerouting",
        path / "freerouting.exe",
        path / "bin" / "freerouting.exe",
    ):
        if inner.is_file():
            return inner
    raise FreeroutingMissingError(
        f"{path} is a folder with no Freerouting launcher in it; point CADGEN_FREEROUTING at the launcher or the "
        f"jar ({freerouting_hint()})"
    )


def _tool(path: Path) -> Freerouting:
    if path.suffix.lower() == ".jar":
        java, version = _find_java()
        return Freerouting(command=(str(java), "-Djava.awt.headless=true", "-jar", str(path)), location=path, java_version=version)
    return Freerouting(command=(str(_launcher(path)),), location=path)


def _install_candidates() -> list[Path]:
    found: list[Path] = []
    if sys.platform == "darwin":
        for root in (Path("/Applications"), Path.home() / "Applications"):
            found.append(root / "freerouting.app" / "Contents" / "MacOS" / "freerouting")
    elif sys.platform.startswith("win"):
        local = os.environ.get("LOCALAPPDATA", "")
        program_files = os.environ.get("ProgramFiles", r"C:\Program Files")
        if local:
            found.extend([Path(local) / "freerouting" / "freerouting.exe", Path(local) / "Programs" / "freerouting" / "freerouting.exe"])
        found.append(Path(program_files) / "freerouting" / "freerouting.exe")
    else:
        found.append(Path("/opt/freerouting/bin/freerouting"))
    return found


def find_freerouting() -> Freerouting:
    """The Freerouting this process runs, or :class:`FreeroutingMissingError` saying how to get one."""
    explicit = os.environ.get("CADGEN_FREEROUTING", "").strip()
    if explicit:
        path = Path(explicit).expanduser()
        if not path.exists():
            raise FreeroutingMissingError(
                f"CADGEN_FREEROUTING is {explicit}, which does not exist; point it at Freerouting's jar or its "
                f"launcher, or unset it ({freerouting_hint()})"
            )
        return _tool(path)
    on_path = shutil.which("freerouting")
    if on_path:
        return _tool(Path(on_path))
    for candidate in _install_candidates():
        if candidate.is_file():
            return _tool(candidate)
    raise FreeroutingMissingError(f"board.autoroute() needs Freerouting, which was not found: {freerouting_hint()}")


# Freerouting asks GitHub for its latest release on every start, and has no setting
# that stops it. Its HTTP client honours Java's proxy properties, so a proxy at a
# closed local port makes the request fail on this machine: a build never reaches
# the network. JAVA_TOOL_OPTIONS reaches the JVM inside Freerouting's own app
# launchers as well as a jar cadgen starts.
_OFFLINE_JAVA = ("-Dhttps.proxyHost=127.0.0.1", "-Dhttps.proxyPort=9", "-Dhttp.proxyHost=127.0.0.1", "-Dhttp.proxyPort=9")


def _isolated_env() -> dict[str, str]:
    """This process's environment, less Freerouting's own setting overrides, and offline."""
    env = {key: value for key, value in os.environ.items() if not key.upper().startswith("FREEROUTING__")}
    env["JAVA_TOOL_OPTIONS"] = " ".join([*env.get("JAVA_TOOL_OPTIONS", "").split(), *_OFFLINE_JAVA])
    return env


def _tail(text: str) -> str:
    lines = [line for line in (text or "").splitlines() if line.strip()]
    return "\n    ".join(lines[-_TAIL_LINES:])


def _version(output: str) -> tuple[int, ...] | None:
    match = re.search(r"Freerouting v(\d+)\.(\d+)\.(\d+)", output or "")
    return tuple(int(part) for part in match.groups()) if match else None


def run_freerouting(tool: Freerouting, *, dsn: Path, ses: Path, passes: int, timeout: float, folder: Path) -> str:
    """Route ``dsn`` into ``ses`` with ``tool``; returns Freerouting's version. Raises on a failed run."""
    user_data = folder / "freerouting-settings"
    command = [
        *tool.command,
        "-de", str(dsn),
        "-do", str(ses),
        "-mp", str(int(passes)),
        "-mt", "1",
        "-da",
        "--gui.enabled=false",
        f"--user_data_path={user_data}",
        "--logging.file.enabled=false",
        # A trace keeps its net class's width all the way to the pad: a necked-down
        # trace can fall under the board's minimum width, which DRC would refuse.
        "--router.automatic_neckdown=false",
        # The fan-out pre-pass drops escape vias beside every SMD pad (a BGA's
        # need); routing pad to pad uses fewer.
        "--router.fanout.enabled=false",
        "--router.optimizer.max_threads=1",
    ]
    try:
        completed = subprocess.run(
            command,
            cwd=str(folder),
            env=_isolated_env(),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        raise RouteError(
            f"Freerouting did not finish routing in {timeout:g} s, so the build stopped it: lower "
            "board.autoroute(passes=...), route the hardest nets by hand, give the parts more room, or raise "
            "timeout=..."
        ) from None
    except OSError as error:
        raise RouteError(f"Freerouting could not be started ({error}): {' '.join(tool.command)}") from None
    output = (completed.stdout or "") + (completed.stderr or "")
    version = _version(output)
    if version is not None and version < FREEROUTING_MINIMUM:
        raise FreeroutingMissingError(
            f"{tool.location} is Freerouting {'.'.join(map(str, version))}; cadgen needs "
            f"{'.'.join(map(str, FREEROUTING_MINIMUM))} or newer: {freerouting_hint()}"
        )
    if "UnsupportedClassVersionError" in output:
        raise FreeroutingMissingError(
            f"{tool.location} needs a newer Java than the one that ran it: install Java {JAVA_MAJOR} or newer and "
            "set CADGEN_JAVA or JAVA_HOME to it"
        )
    if "Failed to apply CLI router setting" in output:
        raise RouteError(
            f"Freerouting at {tool.location} refused a setting cadgen routes with, so its routes would not follow "
            f"the board's rules; use Freerouting {'.'.join(map(str, FREEROUTING_MINIMUM))} or newer:\n    {_tail(output)}"
        )
    if completed.returncode != 0 or not ses.is_file() or ses.stat().st_size == 0:
        raise RouteError(
            f"Freerouting failed (exit status {completed.returncode}) and wrote no routes:\n    {_tail(output)}"
        )
    return ".".join(map(str, version)) if version is not None else "unknown"


# --- a board, routed ------------------------------------------------------------------------


@dataclass(frozen=True)
class Routed:
    """A board tree with Freerouting's tracks and vias added, and what was added."""

    tree: list
    routes: Routes
    freerouting: str


def route_board(board: Board, pcb_tree: list, *, project: str, name: str, tool: Freerouting | None = None) -> Routed:
    """``pcb_tree`` (the board's ``.kicad_pcb`` tree) routed as ``board.autoroute(...)`` asked.

    The DSN is written and Freerouting run in a temporary folder; the tracks
    and vias it added come back with UUIDs derived from their place in the
    routes, so the same routes always write the same board.
    """
    request = board.autoroute_request
    if request is None:
        raise DesignError("route_board needs a board that asked for routing: call board.autoroute()")
    # The written board spells nets as KiCad does (TX/RX is TX{slash}RX).
    skip = [kicad_net_name(item.name if isinstance(item, Net) else str(item).strip()) for item in request.skip]
    dsn = board_dsn(pcb_tree, project, skip=skip, layers=request.layers, name=name, host_version=cadgen.__version__)
    if not dsn.routed:
        return Routed(tree=pcb_tree, routes=Routes(tracks=(), vias=()), freerouting="")
    tool = tool or find_freerouting()
    with tempfile.TemporaryDirectory(prefix="cadgen-route-") as staging:
        folder = Path(staging)
        dsn_path, ses_path = folder / f"{name}.dsn", folder / f"{name}.ses"
        dsn_path.write_text(dsn.text, encoding="utf-8")
        version = run_freerouting(tool, dsn=dsn_path, ses=ses_path, passes=request.passes, timeout=request.timeout, folder=folder)
        try:
            routes = read_session(ses_path.read_text(encoding="utf-8"), dsn)
        except SessionError as error:
            raise RouteError(f"Freerouting {version} answered with a session cadgen cannot use: {error}") from None
    return Routed(tree=with_routes(pcb_tree, routes, project=name), routes=routes, freerouting=version)
