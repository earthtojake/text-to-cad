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
running there is stopped once it ends (``stop_engine``). Its ``CADGEN_CACHE_DIR`` is a folder
of its own that does not exist, so nothing a test starts reaches a developer's cadgen 0.7
store. The per-module output is printed as
each finishes and the final ``Ran N tests`` / ``OK`` / ``FAILED`` summary aggregates every
module. The loaded test set is identical to `python -m unittest <files>` run from --top. A
file still running ``FILE_HANG_SECONDS`` after it started is hung: its interpreter prints
every thread's stack and exits, and the run fails naming the file.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import faulthandler
import importlib
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
# A file's engine daemon goes when the file ends (``stop_engine``); one a killed run leaves
# behind goes away on its own after this long idle.
ENGINE_IDLE_SECONDS = 300
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


def run_in_process(files: list[str], top: str, verbose: bool, hang_seconds: float | None = None) -> int:
    if hang_seconds:
        faulthandler.dump_traceback_later(hang_seconds, exit=True)
    top = os.path.realpath(top)
    # `python -m unittest` runs with sys.path[0] == "" (the cwd); `python <script>`
    # puts the SCRIPT's directory there instead. Match -m so tests see the same path.
    sys.path[0] = ""

    loader = unittest.TestLoader()
    suite = unittest.TestSuite(load_file(loader, path, top) for path in files)
    runner = unittest.TextTestRunner(
        verbosity=2 if verbose else 1,
        # unittest.main enables the default warning filter unless -W was given.
        warnings=None if sys.warnoptions else "default",
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
    if not any(name.endswith((".sock", ".port")) for name in names):
        return
    env = {**os.environ, "CADGEN_ENGINE_DIR": engine_dir,
           "PYTHONPATH": os.pathsep.join(filter(None, [os.path.join(top, "packages", "cadgen", "src"),
                                                       os.environ.get("PYTHONPATH", "")]))}
    stopped = subprocess.run([sys.executable, "-P", "-c", "from cadgen.engine import api; api.stop()"],
                             env=env, capture_output=True, text=True, timeout=ENGINE_STOP_SECONDS)
    if stopped.returncode:
        raise RuntimeError(f"the test engine daemon in {engine_dir} did not stop: {stopped.stdout}{stopped.stderr}")


def _run_one_file(path: str, top: str, verbose: bool, env: dict[str, str]) -> tuple[str, int, str, float]:
    started = time.perf_counter()
    try:
        return _run_file(path, top, verbose, env, started)
    finally:
        stop_engine(top, env["CADGEN_ENGINE_DIR"])


def _run_file(path: str, top: str, verbose: bool, env: dict[str, str], started: float) -> tuple[str, int, str, float]:
    argv = [sys.executable, os.path.abspath(__file__), "--top", top, "--file",
            "--hang-seconds", str(FILE_HANG_SECONDS)]
    if verbose:
        argv.append("--verbose")
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
    # Short: a Unix socket path caps near 104 bytes, and the engine's sits in this folder.
    engines = tempfile.mkdtemp(prefix="cgt-")
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=jobs) as pool:
            futures = []
            for index, path in enumerate(files):
                # A state folder of its own too: the engine's registry of documents (and Recents)
                # never reaches the person's.
                env = {**os.environ, "CADGEN_ENGINE_DIR": os.path.join(engines, f"e{index}"),
                       "CADGEN_STATE_DIR": os.path.join(engines, f"s{index}"),
                       "CADGEN_CACHE_DIR": os.path.join(engines, f"c{index}"),
                       "CADGEN_ENGINE_IDLE": str(ENGINE_IDLE_SECONDS)}
                futures.append(pool.submit(_run_one_file, path, top, verbose, env))
            for future in concurrent.futures.as_completed(futures):
                path, code, output, seconds = future.result()
                durations.append((path, seconds))
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
    ok = not failed_modules and not unparsed and totals["failures"] == 0 and totals["errors"] == 0
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
    parser.add_argument("files", nargs="+", metavar="TEST_FILE")
    args = parser.parse_args(argv)

    if args.file:
        return run_in_process(args.files, args.top, args.verbose, args.hang_seconds)
    return run_files(args.files, args.top, max(1, args.jobs), args.verbose, args.print_weights)


if __name__ == "__main__":
    sys.exit(main())
