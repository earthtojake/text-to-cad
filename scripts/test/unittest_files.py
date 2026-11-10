"""Run unittest over an explicit list of test FILES, each under its dotted package path.

`python -m unittest tests/python/skills/cad/run/test_cli.py` does load the module by its
dotted path, but when that import fails it reports the failure under the LAST component
only -- `ERROR: test_cli (unittest.loader._FailedTest.test_cli)` -- so the three
`test_cli.py` files under different packages are indistinguishable in the summary, and
a SyntaxError in any one of them aborts the whole run before a single test executes.

This entrypoint imports each file under the dotted name of its path relative to --top
(what `-m unittest` does), and turns a failed import into ONE failing test named by
that full dotted path whose message carries the file and the traceback. It also refuses
a module that resolved to a DIFFERENT file than the one asked for (a sys.path shadow),
which `-m unittest` would run silently.

    python scripts/test/unittest_files.py --top <repo root> [--jobs N] [--shard I/N] <test file>...

``--print-weights`` prints this run's measured per-file costs, the first thing to read
when a run is slow. ``--no-skips`` fails a run in which any test skipped: for a suite whose
CI job exists to run it whole, where a test that skips is a job that passed having checked
nothing.

Each FILE runs in its own interpreter, ``--jobs`` at a time (default one), with an engine
directory of its own (``CAD_ENGINE_DIR``): a build it asks for without naming one runs on
an engine daemon of that file's alone, never on a developer's own, and a daemon the file left
running there is stopped once it ends (``stop_engine``). Its ``CAD_CACHE_DIR``,
``CAD_STATE_DIR`` and ``CAD_LAUNCHER_DIR`` are folders of its own, the state folder holding nothing but
this run's interpreter registered as its current installation (``engine_daemon.register``: the
installation whose engine a client starts, where with none it starts none), so
nothing a test starts reaches a developer's cadgen 0.7 store, their registry of documents, their
installations or their ``cadgen`` command; a record that this run's cadgen writes in the
developer's own state folder anyway, or that command written, fails the run, named with the test
that was running (``person_places``, ``the_run_s``). The run's files share one bytecode folder
(``PYTHONPYCACHEPREFIX``), so the CAD kernel's libraries are compiled once a run, not once a file.
The per-module output is printed as each finishes and the final ``Ran N tests`` / ``OK`` /
``FAILED`` summary aggregates every module. The loaded test set is identical to `python -m
unittest <files>` run from --top.

A file still running ``FILE_HANG_SECONDS`` (``--hang-seconds``) after it started is hung: its
interpreter prints every thread's stack and exits (its guard), and should that guard not fire, the
runner ends the interpreter itself ``FILE_BACKSTOP_SECONDS`` later. Either way the run fails naming
the file, and from then on starts no file it has not started (the ones running finish, each under
its own guard): the summary says how many never ran, and ends ``RUN CUT SHORT``. While files run, a
``still running:`` line on stderr names each with how long it has been running, once a
``HEARTBEAT_SECONDS``, so a run its job's timeout kills still said where it was; a run whose files
all end within that says nothing more.

``--shard I/N`` (``CAD_TEST_SHARD=I/N`` through ``run_python_unittest``) runs one of N shards of the
files given: sorted by path, the k-th (from 0) is shard ``k % N + 1``'s, so each file is in exactly
one shard. A shard none of the files falls to passes, saying so.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import faulthandler
import importlib
import json
import locale
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import unittest

# Hung, not slow: the slowest file CI has measured took about five minutes (290 s, on Windows;
# 170 s on Linux). Without this a hang runs out the CI job's timeout and says nothing about where it
# is; and as the run starts no file after one hung, one hang costs the job this long, not this
# long a file.
FILE_HANG_SECONDS = 10 * 60
# How long past a file's own guard the runner waits before ending its interpreter itself: for a
# child whose guard cannot fire (a test that replaced or cancelled it, an interpreter stopped).
FILE_BACKSTOP_SECONDS = 60
# How often the run names the files still running (``still running:``), on stderr.
HEARTBEAT_SECONDS = 60
# A file's engine daemon goes when the file ends (``stop_engine``): an engine never stops on a
# timer, so one a killed run leaves behind runs until it is stopped (``cad stop`` with its
# folder) or its folder is removed (an engine whose door is gone stops).

# Stopping a file's daemon waits for its workers to exit.
ENGINE_STOP_SECONDS = 120


def dotted_name(path: str, top: str) -> str:
    relative = os.path.relpath(os.path.abspath(path), top)
    if os.path.isabs(relative) or relative.startswith(os.pardir):
        raise SystemExit(f"unittest_files: {path} is not under --top {top}")
    stem, extension = os.path.splitext(relative)
    if extension != ".py":
        raise SystemExit(f"unittest_files: {path} is not a Python file")
    return stem.replace(os.sep, ".").replace("/", ".")


def _synthetic_test(name: str, body) -> unittest.TestCase:
    # A TestCase whose single method is NAMED by the dotted module path, so the
    # id printed in the summary reads `tests.python.skills.cad.run.test_cli`. This is
    # how unittest's own discovery reports a module it could not import.
    case_class = type("_FailedImport", (unittest.TestCase,), {name: body})
    return case_class(name)


def failed_import_test(name: str, path: str, exception_text: str) -> unittest.TestCase:
    message = f"Failed to import test module {name}\n  file: {path}\n{exception_text}"

    def test_failure(self):
        raise ImportError(message)

    return _synthetic_test(name, test_failure)


def skipped_module_test(name: str, reason: str) -> unittest.TestCase:
    def test_skipped(self):
        raise unittest.SkipTest(reason)

    return _synthetic_test(name, test_skipped)


def load_file(loader: unittest.TestLoader, path: str, top: str) -> unittest.TestSuite:
    name = dotted_name(path, top)
    try:
        module = importlib.import_module(name)
    except unittest.SkipTest as skip:
        return unittest.TestSuite([skipped_module_test(name, str(skip))])
    except BaseException as error:  # noqa: BLE001 - a SyntaxError must not abort the run
        if isinstance(error, (KeyboardInterrupt, SystemExit)):
            raise
        return unittest.TestSuite([failed_import_test(name, path, traceback.format_exc())])
    module_file = getattr(module, "__file__", None)
    if not module_file or os.path.realpath(module_file) != os.path.realpath(path):
        return unittest.TestSuite(
            [
                failed_import_test(
                    name,
                    path,
                    f"import resolved to a different file: {module_file!r} "
                    "(another sys.path entry shadows this test module)",
                )
            ]
        )
    return loader.loadTestsFromModule(module)


# What a person's cadgen registers in its state folder (``cad_server.engine.registry``,
# ``cad_server._internal.installations``): documents' records, engines' records and the page token,
# installations' records. A name ending ``.tmp`` is a write in flight (``registry.Folder``).
REGISTERED = ("documents", "engines", "installations")
# A file's line naming what appeared in the developer's own places while one of its tests ran.
OUTSIDE = "OUTSIDE"
_OUTSIDE = re.compile(rf"^{OUTSIDE}\t([^\t\n]*)\t([^\t\n]*)\n?", re.M)


def registered(states: list[str], commands: list[str]) -> dict[str, tuple[int, int] | None]:
    """Each entry registered in the state folders ``states``, by its path, and each of ``commands``
    that exists, by its path with when it was written and its size."""
    marks: dict[str, tuple[int, int] | None] = {}
    for state in states:
        for folder in REGISTERED:
            try:
                names = os.listdir(os.path.join(state, folder))
            except OSError:
                continue
            marks.update((os.path.join(state, folder, name), None) for name in names if not name.endswith(".tmp"))
    for command in commands:
        try:
            written = os.lstat(command)
        except OSError:
            continue
        marks[command] = (written.st_mtime_ns, written.st_size)
    return marks


def gained(before: dict, after: dict) -> list[str]:
    """What ``after`` has that ``before`` had not: an entry new, or a command written again."""
    return sorted(path for path, mark in after.items() if path not in before or before[path] != mark)


class _Watching(unittest.TextTestResult):
    """Says of each test what appeared in the developer's own places while it ran (``OUTSIDE``),
    which the run names it by. A test of another file running beside it saw the same."""

    places: tuple[list[str], list[str]] = ([], [])

    def startTest(self, test):
        self._before = registered(*self.places)
        super().startTest(test)

    def stopTest(self, test):
        super().stopTest(test)
        appeared = gained(self._before, registered(*self.places))
        if appeared:
            sys.__stdout__.write("".join(f"{OUTSIDE}\t{path}\t{test.id()}\n" for path in appeared))
            sys.__stdout__.flush()


_hang_report = None  # the guard's file, kept open: faulthandler writes to it from its own thread


def run_in_process(files: list[str], top: str, verbose: bool, hang_seconds: float | None = None,
                   places: tuple[list[str], list[str]] | None = None, hang_report: str | None = None) -> int:
    global _hang_report
    if hang_seconds:
        # Into a file of the runner's naming, where the runner has one: what is written there is
        # the guard's alone, so the runner knows the guard fired from it, not from what a test said.
        _hang_report = open(hang_report, "w", encoding="utf-8") if hang_report else None  # noqa: SIM115
        faulthandler.dump_traceback_later(hang_seconds, exit=True,
                                          **({"file": _hang_report} if _hang_report else {}))
    top = os.path.realpath(top)
    # `python -m unittest` runs with sys.path[0] == "" (the cwd); `python <script>`
    # puts the SCRIPT's directory there instead. Match -m so tests see the same path.
    sys.path[0] = ""

    loader = unittest.TestLoader()
    suite = unittest.TestSuite(load_file(loader, path, top) for path in files)
    if places:
        _Watching.places = places
    runner = unittest.TextTestRunner(
        verbosity=2 if verbose else 1,
        # unittest.main enables the default warning filter unless -W was given.
        warnings=None if sys.warnoptions else "default",
        resultclass=_Watching if places else None,
    )
    result = runner.run(suite)
    return 0 if result.wasSuccessful() else 1


# The tail of a TextTestRunner run: "Ran N tests in Xs", a blank, then OK / FAILED
# with its parenthesised counts. Parsed off each module's output to aggregate.
_RAN = re.compile(r"^Ran (\d+) tests? in ([\d.]+)s$", re.M)
_TAIL = re.compile(r"^(OK|FAILED)(?: \((.*)\))?$", re.M)


def _counts(output: str) -> dict[str, int]:
    counts = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0, "expected failures": 0, "unexpected successes": 0}
    ran = _RAN.search(output)
    if ran:
        counts["tests"] = int(ran.group(1))
    tail = _TAIL.findall(output)
    if tail:
        _verdict, detail = tail[-1]
        for part in filter(None, (piece.strip() for piece in detail.split(","))):
            key, _, value = part.rpartition("=")
            if key in counts and value.isdigit():
                counts[key] = int(value)
    return counts


# The three packages' source trees under the checkout, the library's first (common.sh's
# PACKAGE_SOURCES): what the run's own helpers import.
SOURCES = (("packages", "cad", "src"), ("packages", "cad-server", "src"),
           ("packages", "cad-mcp", "src"))


def _source_path(top: str) -> str:
    """``PYTHONPATH`` naming the checkout's packages, then whatever this run's already names."""
    return os.pathsep.join(filter(None, [*(os.path.join(top, *source) for source in SOURCES),
                                         os.environ.get("PYTHONPATH", "")]))


def stop_engine(top: str, engine_dir: str) -> None:
    """Stop the engine daemon a file left running in its own engine directory, if it left one."""
    try:
        names = os.listdir(engine_dir)
    except FileNotFoundError:
        return
    if not any(name.endswith((".door", ".port")) for name in names):
        return
    env = {**os.environ, "CAD_ENGINE_DIR": engine_dir, "PYTHONPATH": _source_path(top)}
    stopped = subprocess.run([sys.executable, "-P", "-c", "from cad.engine import api; api.stop()"],
                             env=env, capture_output=True, text=True, timeout=ENGINE_STOP_SECONDS)
    if stopped.returncode:
        raise RuntimeError(f"the test engine daemon in {engine_dir} did not stop: {stopped.stdout}{stopped.stderr}")


def _engine_python(top: str, code: str, **env: str) -> subprocess.CompletedProcess:
    """``code`` run against this checkout's packages, the environment as this run's but ``env``."""
    given = {key: value for key, value in os.environ.items() if key != "CAD_ENGINE_DIR"}
    given["PYTHONPATH"] = _source_path(top)
    return subprocess.run([sys.executable, "-P", "-c", code], env={**given, **env}, capture_output=True, text=True,
                          timeout=ENGINE_STOP_SECONDS)


def default_engine_door(top: str) -> str | None:
    """Where the device's engine has its door when nothing names its folder
    (``places.default_engine_dir``): the developer's own engine's place. None where it cannot be said."""
    found = _engine_python(top, "import os; from cad.engine import places; "
                                "print(os.path.join(places.default_engine_dir(), places.NAME + "
                                "('.port' if os.name == 'nt' else '.door')))")
    return (found.stdout.strip() or None) if found.returncode == 0 else None


def engine_answers(top: str, door: str) -> bool:
    """Whether an engine answers at ``door``'s folder (its file alone may be a dead engine's)."""
    if not os.path.exists(door):
        return False
    found = _engine_python(top, "from cad.engine.client import request; "
                                "print('yes' if request({'op': 'pid'}, start=False) else 'no')",
                           CAD_ENGINE_DIR=os.path.dirname(door))
    return found.stdout.strip() == "yes"


# Where the developer keeps what their own cadgen registers, which no test may write (every file has
# folders of its own): the state folder (``cad_server.viewer.recents.state_dir``) and the ``cadgen``
# command (``cad_server._internal.installations.proxy_path``), as this run's environment names them and
# as the platform does where nothing names them; and the name this run's engines give their records
# there (``places.NAME``: one engine a device, so one record).
_PERSON_PLACES = (
    "import json, os\n"
    "from cad_server._internal.installations import proxy_path\n"
    "from cad.engine import places as engine\n"
    "from cad_server.viewer.recents import state_dir\n"
    "places = [(str(state_dir()), proxy_path())]\n"
    "os.environ.pop('CAD_STATE_DIR', None)\n"
    "os.environ.pop('CAD_LAUNCHER_DIR', None)\n"
    "places.append((str(state_dir()), proxy_path()))\n"
    "print(json.dumps({'places': places, 'engine': engine.NAME}))\n"
)


def person_places(top: str) -> tuple[list[str], list[str], str]:
    """The developer's own state folders and ``cadgen`` commands, and the name this run's engines
    record themselves by there (``_PERSON_PLACES``), as cadgen names them. The run cannot start where
    cadgen cannot say."""
    found = _engine_python(top, _PERSON_PLACES)
    if found.returncode:
        raise SystemExit(f"unittest_files: cadgen cannot say where the developer's state is:\n{found.stderr}")
    said = json.loads(found.stdout)
    return (list(dict.fromkeys(os.path.realpath(state) for state, _command in said["places"])),
            list(dict.fromkeys(os.path.abspath(command) for _state, command in said["places"])),
            said["engine"])


def _within(path: str, folders: list[str]) -> bool:
    return any(path == folder or path.startswith(folder.rstrip(os.sep) + os.sep) for folder in folders)


def the_run_s(where: str, engine: str, top: str) -> bool:
    """Whether what appeared at ``where`` says it is this run's cadgen's, not another one the
    developer ran meanwhile: an engine's record named as this run's engines name theirs (``engine``),
    and the page token; an installation's or a document's record that names a folder of this run's
    -- its interpreter's environment, its temporary folder, the checkout (but ``models/``, which no
    test reads, and the worktrees in ``.claude/``); the ``cadgen`` command, and anything that says
    nothing of itself."""
    folder, name = os.path.split(where)
    kind = os.path.basename(folder)
    if kind == "engines":
        return name in (f"{engine}.json", "token")
    if kind not in ("documents", "installations"):
        return True
    try:
        with open(os.path.join(where, "document.json") if kind == "documents" else where, encoding="utf-8") as record:
            said = json.load(record)
        named = [os.path.realpath(path) for path in ([said["root"]] if kind == "documents"
                                                     else [said["prefix"], said["python"]])]
    except (OSError, ValueError, TypeError, KeyError):
        return True
    ours = [os.path.realpath(tempfile.gettempdir()), os.path.realpath(sys.prefix), top]
    theirs = [os.path.join(top, "models"), os.path.join(top, ".claude")]
    return any(_within(path, ours) and not _within(path, theirs) for path in named)


def _run_one_file(path: str, top: str, verbose: bool, env: dict[str, str],
                  places: tuple[list[str], list[str]] | None = None, hang_seconds: float | None = None,
                  ) -> tuple[str, int, str, float, str | None]:
    """The file run in an interpreter of its own: its path, exit code, output, seconds, and, when
    it hung, how (else None)."""
    started = time.perf_counter()
    try:
        return _run_file(path, top, verbose, env, started, places,
                         FILE_HANG_SECONDS if hang_seconds is None else hang_seconds)
    finally:
        stop_engine(top, env["CAD_ENGINE_DIR"])


def _run_file(path: str, top: str, verbose: bool, env: dict[str, str], started: float,
              places: tuple[list[str], list[str]] | None = None, hang_seconds: float = FILE_HANG_SECONDS,
              ) -> tuple[str, int, str, float, str | None]:
    descriptor, report = tempfile.mkstemp(prefix="cgt-hang-", suffix=".txt")
    os.close(descriptor)
    argv = [sys.executable, os.path.abspath(__file__), "--top", top, "--file",
            "--hang-seconds", str(hang_seconds), "--hang-report", report]
    if verbose:
        argv.append("--verbose")
    if places and any(places):
        argv += ["--places", json.dumps(places)]
    argv.append(path)
    hung = None
    try:
        # Files, not pipes: a process the test started and left running would hold a pipe
        # open, and this run would wait on it however its own interpreter ended.
        with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
            try:
                code = subprocess.run(argv, env=env, stdout=stdout, stderr=stderr, cwd=os.getcwd(),
                                      timeout=hang_seconds + FILE_BACKSTOP_SECONDS).returncode
            except subprocess.TimeoutExpired:  # run() has killed it, and waited for it
                code = 1
                hung = (f"the runner killed it {hang_seconds + FILE_BACKSTOP_SECONDS:g} s after it started: "
                        f"its own {hang_seconds:g} s guard never fired")
            output = "".join(_read_all(stream) for stream in (stdout, stderr))
        with open(report, "rb") as guard:
            stacks = _read_all(guard)
    finally:
        os.remove(report)
    if stacks and hung is None:
        hung = f"its guard fired {hang_seconds:g} s after it started"
    if hung:
        output += (f"\n{path} hung: {hung}"
                   + (f"; every thread's stack as it hung:\n{stacks}" if stacks else "") + "\n")
    return path, code, output, time.perf_counter() - started, hung


def _read_all(stream) -> str:
    stream.seek(0)
    # What `text=True` did to a pipe: its encoding, and universal newlines. A Windows
    # child ends lines with \r\n, and a summary line left ending in \r matches no regex.
    text = stream.read().decode(locale.getpreferredencoding(False), errors="replace")
    return text.replace("\r\n", "\n").replace("\r", "\n")


_SAYING = threading.Lock()  # one writer to stderr at a time: a file's output, a hang, the heartbeat


def _say(text: str) -> None:
    with _SAYING:
        sys.stderr.write(text)
        sys.stderr.flush()


def _shown(path: str, top: str) -> str:
    """``path`` relative to ``top`` where it is under it, else as given."""
    try:
        relative = os.path.relpath(os.path.abspath(path), top)
    except ValueError:  # another drive
        return path
    return path if relative.startswith(os.pardir) else relative


def _heartbeat(started: dict[str, float], lock: threading.Lock, stop: threading.Event, top: str) -> None:
    """Until ``stop``, one ``still running:`` line naming the files running and for how long,
    longest first: once one has run ``HEARTBEAT_SECONDS``, and at most once a ``HEARTBEAT_SECONDS``.
    Looked at sixty times a beat, so a file that runs a little past a beat is still named."""
    said = None  # when the last line was
    while not stop.wait(HEARTBEAT_SECONDS / 60):
        now = time.perf_counter()
        if said is not None and now - said < HEARTBEAT_SECONDS:
            continue
        with lock:
            running = sorted(started.items(), key=lambda entry: (entry[1], entry[0]))
        if running and now - running[0][1] >= HEARTBEAT_SECONDS:
            _say("still running: " + ", ".join(f"{_shown(path, top)} ({now - since:.0f}s)"
                                               for path, since in running) + "\n")
            said = now


def shard(files: list[str], index: int, count: int) -> list[str]:
    """Shard ``index`` of ``count`` (from 1) of ``files``: sorted by path, the k-th (from 0) is
    shard ``k % count + 1``'s."""
    return [path for k, path in enumerate(sorted(files, key=lambda path: (path.replace("\\", "/"), path)))
            if k % count + 1 == index]


def _shard_argument(value: str) -> tuple[int, int]:
    index, slash, count = value.partition("/")
    if slash and index.isdigit() and count.isdigit() and 1 <= int(index) <= int(count):
        return int(index), int(count)
    raise argparse.ArgumentTypeError(f"wants I/N, a shard I of N with 1 <= I <= N (as 2/3), not {value!r}")


def run_files(files: list[str], top: str, jobs: int, verbose: bool, print_weights: bool = False,
              no_skips: bool = False, hang_seconds: float | None = None) -> int:
    top = os.path.realpath(top)
    hang_seconds = FILE_HANG_SECONDS if hang_seconds is None else hang_seconds
    started = time.perf_counter()
    totals = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0, "expected failures": 0, "unexpected successes": 0}
    durations: list[tuple[str, float]] = []
    failed_modules: list[str] = []
    unparsed: list[str] = []
    # A test never writes where the developer's own cadgen keeps its state (``person_places``): what
    # this run's cadgen writes there anyway (``the_run_s``) -- looked for as each file ends, and once
    # more as the run does -- fails the run, named with the tests its files say were running then
    # (``OUTSIDE``), else with the files that were, and is left as it is.
    *places, engine = person_places(top)
    places = tuple(places)
    marks = registered(*places)
    outside: dict[str, str] = {}  # what appeared, and when it was found
    seen_in: dict[str, list[str]] = {}  # what appeared, and the tests running as it did
    # Each file's engine folder is in here, its door beside its lock.
    engines = tempfile.mkdtemp(prefix="cgt-")
    # One bytecode folder for the run (``PYTHONPYCACHEPREFIX``, which the engine honours): the
    # first file's worker compiles the CAD kernel's libraries, and every later engine reads them,
    # where each file's own cache folder would compile them again (seconds a file). A test whose
    # subject is where the engine keeps its bytecode starts that engine without it.
    shared = {} if os.environ.get("PYTHONPYCACHEPREFIX") else {"PYTHONPYCACHEPREFIX": os.path.join(engines, "pycache")}
    # A test never starts an engine where nothing names its folder: that is the developer's own
    # engine's place, and one left there runs on after the run. Checked as each file ends (an engine
    # running there before the run is the developer's, and is left alone); one found is stopped, and
    # fails the run naming the files that were running.
    door = default_engine_door(top)
    developers = door is not None and engine_answers(top, door)
    leaked: list[str] = []
    running: dict[str, float] = {}  # the files whose interpreters are running now, and since when
    lock = threading.Lock()
    # A hung file stops the run starting files: one hang is likely the next file's too, and a job
    # that waits out every file's guard ends at its timeout having said nothing. The ones running
    # when it is found finish under their own guards.
    hung: dict[str, str] = {}  # the files that hung, and how
    not_run: list[str] = []  # the files never started, because one hung

    def run_one(path: str, env: dict[str, str]) -> tuple[str, int, str, float, str | None] | None:
        with lock:
            if hung:
                return None
            running[path] = time.perf_counter()
        try:
            result = _run_one_file(path, top, verbose, env, places=places, hang_seconds=hang_seconds)
            if result[4]:
                with lock:
                    hung[path] = result[4]
                    beside = len(running) - 1
                _say(f"hung: {path}: {result[4]}; the run starts no further file"
                     + (f" ({beside} already running will finish first)" if beside else "") + "\n")
            return result
        finally:
            with lock:
                running.pop(path, None)

    def running_now() -> str:
        with lock:
            return ", ".join(sorted(running)) or "none"

    from tests.python.support.engine_daemon import register

    stop = threading.Event()
    beating = threading.Thread(target=_heartbeat, args=(running, lock, stop, top), name="heartbeat", daemon=True)
    beating.start()
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=jobs) as pool:
            futures = {}
            for index, path in enumerate(files):
                # A state folder and a command folder of its own too: the engine's registry of
                # documents (and Recents), the installations and the ``cadgen`` command are the
                # developer's, never a test's. Its state folder registers the file's interpreter as its
                # current installation, as an installation registers itself: a client starts no engine
                # with none.
                env = {**os.environ, **shared, "CAD_ENGINE_DIR": os.path.join(engines, f"e{index}"),
                       "CAD_STATE_DIR": os.path.join(engines, f"s{index}"),
                       "CAD_CACHE_DIR": os.path.join(engines, f"c{index}"),
                       "CAD_LAUNCHER_DIR": os.path.join(engines, f"l{index}"),
                       # A board is drawn as saved, no kicode fetched, but where a suite runs KiCad (test-kicad.sh).
                       "CAD_KICAD_REFILL": os.environ.get("CAD_KICAD_REFILL", "0")}
                register(env["CAD_STATE_DIR"])
                futures[pool.submit(run_one, path, env)] = path
            for future in concurrent.futures.as_completed(futures):
                result = future.result()
                if result is None:
                    not_run.append(futures[future])
                    continue
                path, code, output, seconds, _hung = result
                durations.append((path, seconds))
                if door is not None and not developers and engine_answers(top, door):
                    beside = running_now()
                    leaked.append(f"{door}, after {path} (running beside it: {beside})")
                    _engine_python(top, "from cad.engine import api; api.stop()", CAD_ENGINE_DIR=os.path.dirname(door))
                for where, test in _OUTSIDE.findall(output):
                    seen_in.setdefault(where, []).append(f"{test} ({path})")
                output = _OUTSIDE.sub("", output)
                now = registered(*places)
                for where in gained(marks, now):
                    beside = running_now()
                    outside.setdefault(where, f"after {path} (running beside it: {beside})")
                marks = now
                counts = _counts(output)
                if not _RAN.search(output):
                    # The interpreter died before unittest could summarise (a crash, a
                    # SystemExit in a module body): count it as one error so the run fails
                    # closed, and show everything it said.
                    unparsed.append(path)
                    counts["errors"] = max(counts["errors"], 1)
                for key in totals:
                    totals[key] += counts[key]
                if code != 0:
                    failed_modules.append(path)
                # Everything but the per-module tail, which the aggregate replaces.
                body = _TAIL.sub("", _RAN.sub("", output)).rstrip()
                if body:
                    _say(body + "\n")
        for where in gained(marks, registered(*places)):
            outside.setdefault(where, "after the run's last file")
    finally:
        stop.set()
        beating.join()
        shutil.rmtree(engines, ignore_errors=True)
    elapsed = time.perf_counter() - started
    if print_weights:
        # stdout is free here: every line of a run goes to stderr. One `WEIGHT` line per
        # slow file, longest first.
        for name, seconds in sorted(durations, key=lambda entry: (-entry[1], entry[0])):
            if seconds >= 5.0:
                sys.stdout.write(f"WEIGHT\t{os.path.relpath(os.path.abspath(name), top)}\t{seconds:.0f}\n")
        sys.stdout.flush()
    sys.stderr.write(f"\n{'-' * 70}\nRan {totals['tests']} tests in {elapsed:.3f}s\n\n")
    verdict_parts = []
    for key in ("failures", "errors", "skipped", "expected failures", "unexpected successes"):
        if totals[key]:
            verdict_parts.append(f"{key}={totals[key]}")
    if leaked:
        sys.stderr.write("a test started an engine where nothing named its folder, and left it running (stopped now):\n"
                         + "".join(f"  {where}\n" for where in leaked))
    # On CI no cadgen but the tests' runs, so all that appeared is theirs; beside a developer's own,
    # what says it is another cadgen's (``the_run_s``) is said and left alone.
    appeared = sorted(set(outside) | set(seen_in))
    tests_wrote = [where for where in appeared if os.environ.get("CI") == "true" or the_run_s(where, engine, top)]
    if tests_wrote:
        found = []
        for where in tests_wrote:
            tests = seen_in.get(where, [])
            when = (f"while {tests[0]} ran" if len(tests) == 1 else
                    f"while one of these ran: {'; '.join(tests)}" if tests else outside[where])
            found.append(f"  {where}, {when}\n")
        sys.stderr.write("a test wrote where the developer's own cadgen keeps its state (left as it is):\n"
                         + "".join(found))
    meanwhile = [where for where in appeared if where not in tests_wrote]
    if meanwhile:
        sys.stderr.write("another cadgen wrote where the developer's own keeps its state meanwhile, by what "
                         "each says of itself (no test's):\n" + "".join(f"  {where}\n" for where in meanwhile))
    skipped = totals["skipped"] if no_skips else 0
    if skipped:
        sys.stderr.write(f"{skipped} test{'s' if skipped != 1 else ''} skipped in a run that takes none "
                         "(--no-skips): each says why above\n")
    ok = (not failed_modules and not unparsed and not leaked and not tests_wrote and not skipped
          and not hung and not not_run and totals["failures"] == 0 and totals["errors"] == 0)
    verdict = "OK" if ok else "FAILED"
    sys.stderr.write(verdict + (f" ({', '.join(verdict_parts)})" if verdict_parts else "") + "\n")
    if failed_modules:
        sys.stderr.write("failing modules:\n" + "".join(f"  {p}\n" for p in sorted(failed_modules)))
    if unparsed:
        sys.stderr.write("modules that produced no unittest summary:\n" + "".join(f"  {p}\n" for p in sorted(unparsed)))
    if hung:
        sys.stderr.write("hung (each one's stacks are with its output above):\n"
                         + "".join(f"  {p}: {how}\n" for p, how in sorted(hung.items())))
    if not_run:
        # Last, so the run's last line: a run cut short is not a short run that passed.
        sys.stderr.write(f"RUN CUT SHORT: {len(not_run)} of the {len(files)} files given never started, because "
                         f"a file hung; the counts above are of the {len(files) - len(not_run)} that ran\n")
    sys.stderr.flush()
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--top", required=True, help="directory the dotted module paths are relative to")
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument(
        "--jobs",
        type=int,
        default=1,
        help="how many test files run at once, each in its own interpreter with an engine directory of its own (default 1)",
    )
    parser.add_argument(
        "--print-weights",
        action="store_true",
        help="print one `WEIGHT<TAB>path<TAB>seconds` line per slow file on stdout",
    )
    parser.add_argument("--no-skips", action="store_true", help="fail the run when any test skipped")
    # The runner's own: the interpreter it starts for one file, which runs it here.
    parser.add_argument("--file", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument(
        "--shard",
        type=_shard_argument,
        metavar="I/N",
        help="run shard I of N (from 1) of the files given: sorted by path, the k-th (from 0) is shard k%%N+1's",
    )
    parser.add_argument(
        "--hang-seconds",
        type=float,
        help=f"a file still running this long after it started is hung (default {FILE_HANG_SECONDS}): its "
             "interpreter prints every thread's stack and exits 1, and the run starts no file after it",
    )
    # The runner's own: where the file's interpreter writes its stacks should it hang.
    parser.add_argument("--hang-report", help=argparse.SUPPRESS)
    # The runner's own: the developer's places its file's tests are watched for (``_Watching``).
    parser.add_argument("--places", type=json.loads, help=argparse.SUPPRESS)
    parser.add_argument("files", nargs="+", metavar="TEST_FILE")
    args = parser.parse_args(argv)

    if args.file:
        return run_in_process(args.files, args.top, args.verbose, args.hang_seconds,
                              tuple(args.places) if args.places else None, args.hang_report)
    files = args.files
    if args.shard:
        index, count = args.shard
        files = shard(files, index, count)
        if not files:
            # Not a collector that found nothing (run_python_unittest fails that before here): the
            # other shards run every file given.
            sys.stderr.write(f"shard {index}/{count}: none of the {len(args.files)} files given is this shard's; "
                             "nothing to run (OK)\n")
            return 0
        sys.stderr.write(f"shard {index}/{count}: {len(files)} of the {len(args.files)} files given\n")
    return run_files(files, args.top, max(1, args.jobs), args.verbose, args.print_weights, args.no_skips,
                     args.hang_seconds)


if __name__ == "__main__":
    sys.exit(main())
