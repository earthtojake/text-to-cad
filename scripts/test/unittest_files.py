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

``--shard I/N`` keeps only this shard's share of the files, so N machines can run one
suite between them. The split is a longest-processing-time packing over the per-file
costs in ``scripts/test/python-test-weights.tsv`` -- a hint table, not an input to
correctness: an unlisted or stale file only lands in a shard that finishes sooner than
its siblings. Every file lands in exactly one shard whatever the table says, and an
empty shard is an error rather than a green run of nothing.
``--print-weights`` prints this run's measured costs, which is how that table is rebuilt.

With ``--jobs N`` greater than one, each FILE runs in its own interpreter, N at a time,
with its own fresh store and private daemon endpoint/auth state. Its daemon is retired
before the temporary directories are removed, so modules cannot see one another's
builds or stop one another's artifact workers. The per-module output is printed as each finishes and
the final ``Ran N tests`` / ``OK`` / ``FAILED`` summary aggregates every module, so a
log reads the same as a single-process run. The loaded test set is identical to
`python -m unittest <files>` run from --top either way.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import importlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
import unittest
import uuid


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


def run_in_process(files: list[str], top: str, verbose: bool) -> int:
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


def _run_one_file(path: str, top: str, verbose: bool) -> tuple[str, int, str, float]:
    started = time.perf_counter()
    store = tempfile.mkdtemp(prefix="cadgen-test-store.")
    # Stores alone do not isolate lazy artifact jobs: a sibling test can stop
    # the shared daemon while this module is reading its package. Keep auth,
    # logs and the actual endpoint private too. The short filename avoids the
    # Unix socket length ceiling; Windows pipe names need explicit uniqueness.
    state = tempfile.mkdtemp(prefix="cgt-")
    env = dict(os.environ)
    env["CADGEN_CACHE_DIR"] = store
    env["CADGEN_DAEMON_STATE_DIR"] = state
    env["CADGEN_DAEMON_SOCKET"] = (rf"\\.\pipe\cadgen-test-{uuid.uuid4().hex}" if os.name == "nt"
                                  else os.path.join(state, "d.sock"))
    argv = [sys.executable, os.path.abspath(__file__), "--top", top, "--jobs", "1"]
    if verbose:
        argv.append("--verbose")
    argv.append(path)
    try:
        completed = subprocess.run(argv, env=env, capture_output=True, text=True, cwd=os.getcwd())
    finally:
        try:
            # No key means no daemon could have bound under this private state.
            if any(name.endswith(".key") for name in os.listdir(state)):
                cleanup_env = dict(env)
                cleanup_env["PYTHONPATH"] = os.pathsep.join(filter(None, [
                    os.path.join(top, "packages", "cadgen", "src"), env.get("PYTHONPATH", "")
                ]))
                cleanup = subprocess.run([
                    sys.executable, os.path.join(top, "tests", "python", "support", "daemon_cleanup.py"),
                    env["CADGEN_DAEMON_SOCKET"],
                ], env=cleanup_env, capture_output=True, text=True, timeout=15)
                if cleanup.returncode:
                    raise RuntimeError(f"test daemon cleanup failed: {cleanup.stdout}{cleanup.stderr}")
        finally:
            shutil.rmtree(store, ignore_errors=True)
            shutil.rmtree(state, ignore_errors=True)
    return path, completed.returncode, (completed.stdout or "") + (completed.stderr or ""), time.perf_counter() - started


WEIGHTS = os.path.join("scripts", "test", "python-test-weights.tsv")
DEFAULT_WEIGHT = 1.0


def read_weights(top: str) -> dict[str, float]:
    """The cost hints, keyed by path relative to --top. A missing table is not an error."""
    weights: dict[str, float] = {}
    try:
        with open(os.path.join(top, WEIGHTS), encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line or line.startswith("#") or "\t" not in line:
                    continue
                path, _, seconds = line.partition("\t")
                try:
                    weights[os.path.normpath(path)] = float(seconds)
                except ValueError:
                    continue
    except OSError:
        pass
    return weights


def shard_files(files: list[str], top: str, index: int, count: int) -> list[str]:
    """This shard's files: longest first into the emptiest bin, ties broken by path.

    Deterministic, so N runs of `--shard i/N` between them run every file exactly once
    however the weights drift.
    """
    weights = read_weights(top)

    def weight(path: str) -> float:
        return weights.get(os.path.normpath(os.path.relpath(os.path.abspath(path), top)), DEFAULT_WEIGHT)

    loads = [0.0] * count
    picked: list[str] = []
    for path in sorted(files, key=lambda path: (-weight(path), path)):
        bin_index = min(range(count), key=lambda i: (loads[i], i))
        if bin_index == index - 1:
            picked.append(path)
        loads[bin_index] += weight(path)
    return sorted(picked)


def run_in_parallel(files: list[str], top: str, jobs: int, verbose: bool, print_weights: bool = False) -> int:
    top = os.path.realpath(top)
    started = time.perf_counter()
    totals = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0, "expected failures": 0, "unexpected successes": 0}
    durations: list[tuple[str, float]] = []
    failed_modules: list[str] = []
    unparsed: list[str] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=jobs) as pool:
        futures = [pool.submit(_run_one_file, path, top, verbose) for path in files]
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
    elapsed = time.perf_counter() - started
    if print_weights:
        # stdout is free here: every line of a run goes to stderr. One `WEIGHT` line per
        # file, for whoever is rebuilding python-test-weights.tsv.
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
        help="run each test file in its own interpreter, this many at a time (default 1: one process)",
    )
    parser.add_argument(
        "--shard",
        metavar="I/N",
        help="run only shard I of N (1-based), packed by scripts/test/python-test-weights.tsv",
    )
    parser.add_argument(
        "--print-weights",
        action="store_true",
        help="print one `WEIGHT<TAB>path<TAB>seconds` line per slow file on stdout",
    )
    parser.add_argument("files", nargs="+", metavar="TEST_FILE")
    args = parser.parse_args(argv)

    files = args.files
    if args.shard:
        index, _, count = args.shard.partition("/")
        if not count.isdigit() or not index.isdigit() or not 1 <= int(index) <= int(count):
            raise SystemExit(f"unittest_files: --shard wants I/N with 1 <= I <= N, not {args.shard!r}")
        files = shard_files(files, os.path.realpath(args.top), int(index), int(count))
        if not files:
            # Fewer files than shards. Silence would report a green shard that ran
            # nothing, which is the failure this runner exists to make impossible.
            raise SystemExit(f"unittest_files: shard {args.shard} of {len(args.files)} files is empty")

    if args.jobs > 1 and len(files) > 1:
        return run_in_parallel(files, args.top, args.jobs, args.verbose, args.print_weights)
    return run_in_process(files, args.top, args.verbose)


if __name__ == "__main__":
    sys.exit(main())
