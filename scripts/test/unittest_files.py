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

    python scripts/test/unittest_files.py --top <repo root> [--jobs N] <test file>...

``--print-weights`` prints this run's measured per-file costs, the first thing to read
when a run is slow.

Each FILE runs in its own interpreter, ``--jobs`` at a time (default one), with an engine
directory of its own (``CADGEN_ENGINE_DIR``): a build it asks for without naming one runs on
an engine daemon of that file's alone, never on a developer's own, and a daemon the file left
running there is stopped once it ends (``stop_engine``). Its ``CADGEN_CACHE_DIR``,
``CADGEN_STATE_DIR`` and ``CADGEN_LAUNCHER_DIR`` are folders of its own that do not exist yet, so
nothing a test starts reaches a developer's cadgen 0.7 store, their registry of documents, their
installations or their ``cadgen`` command; a record that this run's cadgen writes in the
developer's own state folder anyway, or that command written, fails the run, named with the test
that was running (``person_places``, ``the_run_s``). The run's files share one bytecode folder
(``PYTHONPYCACHEPREFIX``), so the CAD kernel's libraries are compiled once a run, not once a file.
The per-module output is printed as each finishes and the final ``Ran N tests`` / ``OK`` /
``FAILED`` summary aggregates every module. The loaded test set is identical to `python -m
unittest <files>` run from --top. A file still running ``FILE_HANG_SECONDS`` after it started is
hung: its interpreter prints every thread's stack and exits, and the run fails naming the file.
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
import time
import traceback
import unittest

# Hung, not slow: the slowest file CI has run took about four minutes. Without this a
# hang runs out the CI job's timeout and says nothing about where it is.
FILE_HANG_SECONDS = 15 * 60
# A file's engine daemon goes when the file ends (``stop_engine``): an engine never stops on a
# timer, so one a killed run leaves behind runs until it is stopped (``cadgen stop`` with its
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


# What a person's cadgen registers in its state folder (``cadgen.engine.registry``,
# ``cadgen._internal.installations``): documents' records, engines' records and the page token,
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


def run_in_process(files: list[str], top: str, verbose: bool, hang_seconds: float | None = None,
                   places: tuple[list[str], list[str]] | None = None) -> int:
    if hang_seconds:
        faulthandler.dump_traceback_later(hang_seconds, exit=True)
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


def stop_engine(top: str, engine_dir: str) -> None:
    """Stop the engine daemon a file left running in its own engine directory, if it left one."""
    try:
        names = os.listdir(engine_dir)
    except FileNotFoundError:
        return
    if not any(name.endswith((".door", ".port")) for name in names):
        return
    env = {**os.environ, "CADGEN_ENGINE_DIR": engine_dir,
           "PYTHONPATH": os.pathsep.join(filter(None, [os.path.join(top, "packages", "cadgen", "src"),
                                                       os.environ.get("PYTHONPATH", "")]))}
    stopped = subprocess.run([sys.executable, "-P", "-c", "from cadgen.engine import api; api.stop()"],
                             env=env, capture_output=True, text=True, timeout=ENGINE_STOP_SECONDS)
    if stopped.returncode:
        raise RuntimeError(f"the test engine daemon in {engine_dir} did not stop: {stopped.stdout}{stopped.stderr}")


def _engine_python(top: str, code: str, **env: str) -> subprocess.CompletedProcess:
    """``code`` run against this checkout's cadgen, the environment as this run's but ``env``."""
    given = {key: value for key, value in os.environ.items() if key != "CADGEN_ENGINE_DIR"}
    given["PYTHONPATH"] = os.pathsep.join(filter(None, [os.path.join(top, "packages", "cadgen", "src"),
                                                        os.environ.get("PYTHONPATH", "")]))
    return subprocess.run([sys.executable, "-P", "-c", code], env={**given, **env}, capture_output=True, text=True,
                          timeout=ENGINE_STOP_SECONDS)


def default_engine_door(top: str) -> str | None:
    """Where the device's engine has its door when nothing names its folder
    (``daemon.default_state_dir``): the developer's own engine's place. None where it cannot be said."""
    found = _engine_python(top, "import os; from cadgen.engine import daemon; "
                                "print(os.path.join(daemon.default_state_dir(), daemon.NAME + "
                                "('.port' if os.name == 'nt' else '.door')))")
    return (found.stdout.strip() or None) if found.returncode == 0 else None


def engine_answers(top: str, door: str) -> bool:
    """Whether an engine answers at ``door``'s folder (its file alone may be a dead engine's)."""
    if not os.path.exists(door):
        return False
    found = _engine_python(top, "from cadgen.engine.client import request; "
                                "print('yes' if request({'op': 'pid'}, start=False) else 'no')",
                           CADGEN_ENGINE_DIR=os.path.dirname(door))
    return found.stdout.strip() == "yes"


# Where the developer keeps what their own cadgen registers, which no test may write (every file has
# folders of its own): the state folder (``cadgen.viewer.recents.state_dir``) and the ``cadgen``
# command (``cadgen._internal.installations.proxy_path``), as this run's environment names them and
# as the platform does where nothing names them; and the name this run's engines give their records
# there (``daemon.NAME``: one engine a device, so one record).
_PERSON_PLACES = (
    "import json, os\n"
    "from cadgen._internal.installations import proxy_path\n"
    "from cadgen.engine import daemon\n"
    "from cadgen.viewer.recents import state_dir\n"
    "places = [(str(state_dir()), proxy_path())]\n"
    "os.environ.pop('CADGEN_STATE_DIR', None)\n"
    "os.environ.pop('CADGEN_LAUNCHER_DIR', None)\n"
    "places.append((str(state_dir()), proxy_path()))\n"
    "print(json.dumps({'places': places, 'engine': daemon.NAME}))\n"
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
                  places: tuple[list[str], list[str]] | None = None) -> tuple[str, int, str, float]:
    started = time.perf_counter()
    try:
        return _run_file(path, top, verbose, env, started, places)
    finally:
        stop_engine(top, env["CADGEN_ENGINE_DIR"])


def _run_file(path: str, top: str, verbose: bool, env: dict[str, str], started: float,
              places: tuple[list[str], list[str]] | None = None) -> tuple[str, int, str, float]:
    argv = [sys.executable, os.path.abspath(__file__), "--top", top, "--file",
            "--hang-seconds", str(FILE_HANG_SECONDS)]
    if verbose:
        argv.append("--verbose")
    if places and any(places):
        argv += ["--places", json.dumps(places)]
    argv.append(path)
    # Files, not pipes: a process the test started and left running would hold a pipe
    # open, and this run would wait on it however its own interpreter ended.
    with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
        completed = subprocess.run(argv, env=env, stdout=stdout, stderr=stderr, cwd=os.getcwd())
        output = "".join(_read_all(stream) for stream in (stdout, stderr))
    return path, completed.returncode, output, time.perf_counter() - started


def _read_all(stream) -> str:
    stream.seek(0)
    # What `text=True` did to a pipe: its encoding, and universal newlines. A Windows
    # child ends lines with \r\n, and a summary line left ending in \r matches no regex.
    text = stream.read().decode(locale.getpreferredencoding(False), errors="replace")
    return text.replace("\r\n", "\n").replace("\r", "\n")


def run_files(files: list[str], top: str, jobs: int, verbose: bool, print_weights: bool = False) -> int:
    top = os.path.realpath(top)
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
    running: set[str] = set()  # the files whose interpreters are running now

    def run_one(path: str, env: dict[str, str]) -> tuple[str, int, str, float]:
        running.add(path)
        try:
            return _run_one_file(path, top, verbose, env, places=places)
        finally:
            running.discard(path)
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=jobs) as pool:
            futures = []
            for index, path in enumerate(files):
                # A state folder and a command folder of its own too: the engine's registry of
                # documents (and Recents), the installations and the ``cadgen`` command are the
                # developer's, never a test's.
                env = {**os.environ, **shared, "CADGEN_ENGINE_DIR": os.path.join(engines, f"e{index}"),
                       "CADGEN_STATE_DIR": os.path.join(engines, f"s{index}"),
                       "CADGEN_CACHE_DIR": os.path.join(engines, f"c{index}"),
                       "CADGEN_LAUNCHER_DIR": os.path.join(engines, f"l{index}")}
                futures.append(pool.submit(run_one, path, env))
            for future in concurrent.futures.as_completed(futures):
                path, code, output, seconds = future.result()
                durations.append((path, seconds))
                if door is not None and not developers and engine_answers(top, door):
                    beside = ", ".join(sorted(running)) or "none"
                    leaked.append(f"{door}, after {path} (running beside it: {beside})")
                    _engine_python(top, "from cadgen.engine import api; api.stop()", CADGEN_ENGINE_DIR=os.path.dirname(door))
                for where, test in _OUTSIDE.findall(output):
                    seen_in.setdefault(where, []).append(f"{test} ({path})")
                output = _OUTSIDE.sub("", output)
                now = registered(*places)
                for where in gained(marks, now):
                    beside = ", ".join(sorted(running)) or "none"
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
                    sys.stderr.write(body + "\n")
        for where in gained(marks, registered(*places)):
            outside.setdefault(where, "after the run's last file")
    finally:
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
    ok = (not failed_modules and not unparsed and not leaked and not tests_wrote
          and totals["failures"] == 0 and totals["errors"] == 0)
    verdict = "OK" if ok else "FAILED"
    sys.stderr.write(verdict + (f" ({', '.join(verdict_parts)})" if verdict_parts else "") + "\n")
    if failed_modules:
        sys.stderr.write("failing modules:\n" + "".join(f"  {p}\n" for p in sorted(failed_modules)))
    if unparsed:
        sys.stderr.write("modules that produced no unittest summary:\n" + "".join(f"  {p}\n" for p in sorted(unparsed)))
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
    # The runner's own: the interpreter it starts for one file, which runs it here.
    parser.add_argument("--file", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument(
        "--hang-seconds",
        type=float,
        help="print every thread's stack and exit 1 if the run is still going after this long",
    )
    # The runner's own: the developer's places its file's tests are watched for (``_Watching``).
    parser.add_argument("--places", type=json.loads, help=argparse.SUPPRESS)
    parser.add_argument("files", nargs="+", metavar="TEST_FILE")
    args = parser.parse_args(argv)

    if args.file:
        return run_in_process(args.files, args.top, args.verbose, args.hang_seconds,
                              tuple(args.places) if args.places else None)
    return run_files(args.files, args.top, max(1, args.jobs), args.verbose, args.print_weights)


if __name__ == "__main__":
    sys.exit(main())
