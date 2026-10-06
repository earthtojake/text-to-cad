#!/usr/bin/env python3
"""The cloud runner: one job inside a single-use sandbox.

    python run.py JOB_DIR

JOB_DIR holds ``request.json`` and ``workspace/`` (the build's files). The runner runs
the job with the workspace as its working directory, then writes ``out/`` and
``result.json`` beside them. While it works it prints JSON lines on stdout:
``{"type": "progress", ...}`` relayed from cadgen's build events and
``{"type": "log", "text": ...}`` for everything else.

Jobs:

* ``build``    run each entry script (none for a files-only build), keep what they
               wrote (the outputs), record the viewer export of every viewable file
               (inputs included) and render a thumbnail of the primary one.
* ``snapshot`` ``cadgen snapshot FILE out/snapshot.<png|svg> ARGS --json``.
* ``inspect``  run a Python script against the workspace; images it writes under
               ``workspace/tmp/`` come back.

Standard library only. cadgen is reached through its public command line
(``python -m cadgen.cli``) and through the model scripts themselves, never imported
here. ``result.json`` lists every file the server should collect, with sizes and
SHA-256 digests; the server re-checks all of it, because whatever runs in the
sandbox could have rewritten this file too.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

TAIL_BYTES = 64 * 1024
LINE_LIMIT = 16 * 1024
SITE_DIR = Path(__file__).resolve().parent / "site"

VIEWABLE = (".step", ".stp", ".glb", ".stl", ".3mf", ".dxf", ".urdf", ".sdf", ".srdf")
# What a build may leave behind: CAD documents, their sidecars, meshes and drawings.
# Anything else it writes is dropped (and named in the result), so a build is not a
# general-purpose file host.
OUTPUT_SUFFIXES = set(VIEWABLE) | {
    ".json", ".gltf", ".bin", ".obj", ".ply", ".dae", ".svg", ".pdf", ".png", ".jpg",
    ".jpeg", ".csv", ".txt", ".xml", ".xacro", ".yaml", ".yml", ".mtl",
}
IMAGE_SUFFIXES = (".png", ".svg", ".jpg", ".jpeg")
SKIP_DIRS = {"__pycache__", ".git", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".venv", "node_modules"}
SNAPSHOT_FLAGS_WITH_VALUE = {
    "--mode", "--section", "--camera", "--display", "--kinematics", "--animation", "--time",
    "--joint-values", "--focus", "--hide", "--width", "--height", "--size-profile",
}
SNAPSHOT_FLAGS_BARE = {"--view-labels", "--debug"}
MAX_INSPECT_IMAGES = 8
MAX_IMAGE_BYTES = 10 * 1024 * 1024
THUMBNAIL_SECONDS = 180

_emit_lock = threading.Lock()


def emit(message: dict) -> None:
    line = json.dumps(message, separators=(",", ":"))
    with _emit_lock:
        try:
            sys.stdout.write(line + "\n")
            sys.stdout.flush()
        except (OSError, ValueError):
            pass


class Tail:
    """The last ``limit`` bytes of a text stream, kept whole-line where possible."""

    def __init__(self, limit: int = TAIL_BYTES) -> None:
        self.limit = limit
        self.parts: list[str] = []
        self.size = 0
        self.lock = threading.Lock()

    def add(self, text: str) -> None:
        with self.lock:
            self.parts.append(text)
            self.size += len(text)
            while self.size > self.limit * 2 and len(self.parts) > 1:
                self.size -= len(self.parts.pop(0))

    def text(self) -> str:
        with self.lock:
            joined = "".join(self.parts)
        if len(joined.encode("utf-8")) <= self.limit:
            return joined
        cut = joined.encode("utf-8")[-self.limit:].decode("utf-8", "ignore")
        newline = cut.find("\n")
        return cut[newline + 1:] if 0 <= newline < 200 else cut


LOG = Tail()


def log(text: str) -> None:
    LOG.add(text if text.endswith("\n") else text + "\n")
    emit({"type": "log", "text": text.rstrip("\n")[:LINE_LIMIT]})


class Step:
    def __init__(self, name: str) -> None:
        self.name = name
        self.exit_code: int | None = None
        self.timed_out = False
        self.ms = 0
        self.stdout = Tail()
        self.stderr = Tail()
        self.stderr_lines: list[str] = []


def _kill(process: subprocess.Popen) -> None:
    try:
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGKILL)
        else:
            process.kill()
    except (OSError, ProcessLookupError):
        pass


def run_step(name, argv, *, cwd, env, deadline, on_stderr=None, on_stdout=None, keep_stderr_lines=400) -> Step:
    """Run one child to completion or to ``deadline``, relaying its lines as they come."""
    step = Step(name)
    started = time.monotonic()
    remaining = deadline - started
    if remaining <= 1:
        step.timed_out = True
        step.exit_code = -1
        return step
    options = {"start_new_session": True} if os.name == "posix" else {
        "creationflags": getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)}
    process = subprocess.Popen(
        argv, cwd=str(cwd), env=env, stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, **options,
    )

    def pump(stream, tail: Tail, callback, keep: list[str] | None) -> None:
        for raw in iter(lambda: stream.readline(LINE_LIMIT), b""):
            text = raw.decode("utf-8", "replace")
            consumed = False
            if callback is not None:
                try:
                    consumed = bool(callback(text.rstrip("\n")))
                except Exception:  # noqa: BLE001 - relaying is best effort
                    consumed = False
            if consumed:
                continue  # a progress event: relayed, and not part of the output
            tail.add(text)
            if keep is not None:
                keep.append(text.rstrip("\n"))
                if len(keep) > keep_stderr_lines:
                    del keep[: len(keep) - keep_stderr_lines]
        stream.close()

    threads = [
        threading.Thread(target=pump, args=(process.stdout, step.stdout, on_stdout, None), daemon=True),
        threading.Thread(target=pump, args=(process.stderr, step.stderr, on_stderr, step.stderr_lines), daemon=True),
    ]
    for thread in threads:
        thread.start()
    try:
        process.wait(timeout=max(1.0, remaining))
    except subprocess.TimeoutExpired:
        step.timed_out = True
        _kill(process)
        process.wait()
    else:
        # The child is gone; anything it left running in its group goes with it.
        if os.name == "posix":
            _kill(process)
    for thread in threads:
        thread.join(timeout=5)
    step.exit_code = process.returncode
    step.ms = int((time.monotonic() - started) * 1000)
    return step


# --- errors ---------------------------------------------------------------------------

_FAILED = re.compile(r"^\[[^\]]+\] FAILED: (?P<message>.+)$")
_FRAME = re.compile(r"^\[[^\]]+\]\s+(?P<file>\S.*?):(?P<line>\d+) in (?P<function>.+)$")
_RAISED = re.compile(r"^\[[^\]]+\]\s+raised in (?P<file>\S.*?):(?P<line>\d+)$")
_TB_FILE = re.compile(r'^\s*File "(?P<file>[^"]+)", line (?P<line>\d+)')


def _relative(path_text: str, roots: list[Path]) -> str | None:
    """``path_text`` as a POSIX path relative to the first of ``roots`` holding it, or None.

    A relative path is read against the first root (cadgen prints model frames relative
    to the working directory), and only an existing file counts.
    """
    try:
        candidate = Path(path_text)
        if not candidate.is_absolute():
            candidate = roots[0] / candidate
        resolved = candidate.resolve()
        if not resolved.is_file():
            return None
    except (OSError, ValueError):
        return None
    for root in roots:
        try:
            return resolved.relative_to(root.resolve()).as_posix()
        except ValueError:
            continue
    return None


def parse_error(lines: list[str], roots: list[Path], fallback: str) -> dict:
    """The failure a child reported: cadgen's one-line report and its model frames, or a
    Python traceback. ``file`` and ``line`` name the innermost frame inside ``roots``."""
    error: dict = {"message": fallback, "file": None, "line": None}
    failed_at = None
    for index, line in enumerate(lines):
        match = _FAILED.match(line)
        if match:
            failed_at = index
            error["message"] = match.group("message").strip()
    if failed_at is not None:
        for line in lines[failed_at + 1:]:
            match = _FRAME.match(line) or _RAISED.match(line)
            if match:
                where = _relative(match.group("file"), roots)
                if where is not None:
                    error["file"], error["line"] = where, int(match.group("line"))
        return error
    last_frame = None
    for index, line in enumerate(lines):
        match = _TB_FILE.match(line)
        if match:
            last_frame = index
            where = _relative(match.group("file"), roots)
            if where is not None:
                error["file"], error["line"] = where, int(match.group("line"))
    tail = lines[last_frame + 1:] if last_frame is not None else lines
    for line in reversed(tail):
        if line and not line.startswith((" ", "\t")) and not line.startswith("{"):
            error["message"] = line.strip()
            break
    return error


# --- files ------------------------------------------------------------------------------

def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _skipped_dir(name: str) -> bool:
    return name in SKIP_DIRS or name.startswith(".cadgen")


def scan(root: Path, *, skip_tmp: bool = True, hash_limit: int | None = None) -> dict[str, tuple[int, str]]:
    """Every regular file under ``root``: relative POSIX path -> (bytes, sha256).

    Symlinks are never followed or reported: a job's outputs are files it wrote. A file
    larger than ``hash_limit`` is not read (its digest is empty): it is over the cap.
    """
    found: dict[str, tuple[int, str]] = {}
    if not root.is_dir():
        return found
    for directory, dirnames, filenames in os.walk(root, followlinks=False):
        here = Path(directory)
        relative_dir = here.relative_to(root)
        dirnames[:] = sorted(
            name for name in dirnames
            if not _skipped_dir(name)
            and not (skip_tmp and relative_dir == Path(".") and name == "tmp")
            and not (here / name).is_symlink()
        )
        for name in sorted(filenames):
            path = here / name
            if path.is_symlink() or not path.is_file() or name.endswith((".pyc", ".pyo")):
                continue
            relative = path.relative_to(root).as_posix()
            size = path.stat().st_size
            found[relative] = (size, "" if hash_limit is not None and size > hash_limit else sha256_file(path))
    return found


def changed(before: dict, after: dict) -> list[str]:
    return sorted(path for path, info in after.items() if before.get(path) != info)


def file_entry(job_dir: Path, path: Path) -> dict:
    return {
        "path": path.relative_to(job_dir).as_posix(),
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }


STEP_SUFFIXES = (".step", ".stp")


def pick_primary(viewable: list[str], entries: list[str]) -> str | None:
    """The file a build's link opens: the STEP named for the first entry, else the
    shallowest STEP, else the first viewable file (shallowest, then by path)."""
    order = lambda path: (path.count("/"), path)  # noqa: E731 - one sort key, three uses
    steps = [path for path in viewable if path.lower().endswith(STEP_SUFFIXES)]
    if entries:
        stem = Path(entries[0]).stem.lower()
        named = [path for path in steps if Path(path).stem.lower() == stem]
        if named:
            return min(named, key=order)
    if steps:
        return min(steps, key=order)
    return min(viewable, key=order) if viewable else None


# --- jobs -------------------------------------------------------------------------------

class Job:
    def __init__(self, job_dir: Path) -> None:
        self.dir = job_dir.resolve()
        self.workspace = self.dir / "workspace"
        self.out = self.dir / "out"
        self.request = json.loads((self.dir / "request.json").read_text(encoding="utf-8"))
        self.kind = str(self.request.get("kind") or "")
        self.started = time.monotonic()
        timeout = float(self.request.get("timeoutSeconds") or 600)
        self.deadline = self.started + max(5.0, timeout)
        self.vcpus = int(self.request.get("vcpus") or os.cpu_count() or 1)
        limits = self.request.get("limits") or {}
        self.max_output_bytes = int(limits.get("maxOutputBytes") or 200 * 1024 * 1024)
        self.max_output_files = int(limits.get("maxOutputFiles") or 2000)
        self.flag_dir = self.dir / "flags"
        self.result: dict = {
            "ok": False, "kind": self.kind, "exitCode": None, "wallMs": 0, "error": None,
            "log": "", "stdout": "", "stderr": "", "outputs": [], "dropped": [], "primary": None,
            "export": None, "exportError": None, "thumbnail": None, "images": [],
            "flags": {"network": False}, "cadgen": _cadgen_version(), "files": [], "steps": [],
        }

    def env(self, pythonpath: list[str] | None = None) -> dict:
        env = dict(os.environ)
        paths = [str(SITE_DIR)] + [str(self.workspace / entry) for entry in (pythonpath or [])]
        if env.get("PYTHONPATH"):
            paths.append(env["PYTHONPATH"])  # where this interpreter found cadgen, if not installed
        env.update({
            "CADGEN_DAEMON": "0",
            "CADGEN_CACHE_DIR": str(self.dir / "store"),
            "CADGEN_STATE_DIR": str(self.dir / "state"),
            "CADGEN_JOBS": str(max(1, self.vcpus)),
            "DO_NOT_TRACK": "1",
            "CADGEN_ANALYTICS": "0",
            "CADGEN_UPDATE_CHECK": "0",
            "PYTHONPATH": os.pathsep.join(paths),
            "PYTHONUNBUFFERED": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
            "MPLBACKEND": "Agg",
            "T2C_FLAG_DIR": str(self.flag_dir),
        })
        return env

    def cadgen(self, *args: str) -> list[str]:
        return [sys.executable, "-m", "cadgen.cli", *args]

    def record(self, step: Step) -> None:
        self.result["steps"].append({
            "name": step.name, "exitCode": step.exit_code, "ms": step.ms, "timedOut": step.timed_out,
        })

    def collect(self, path: Path) -> None:
        self.result["files"].append(file_entry(self.dir, path))

    def fail(self, message: str, *, kind: str = "model", file: str | None = None, line: int | None = None) -> None:
        self.result["ok"] = False
        self.result["error"] = {"message": message[:4000], "file": file, "line": line, "kind": kind}

    def timeout_message(self) -> str:
        seconds = int(self.request.get("timeoutSeconds") or 600)
        return f"The job ran out of time: it is limited to {seconds} s."


def _cadgen_version() -> str | None:
    try:
        from importlib.metadata import version

        return version("cadgen")
    except Exception:  # noqa: BLE001 - absent or broken metadata is not fatal
        return None


def _relay_build_event(job: Job, entry: str):
    def relay(line: str) -> None:
        if line.startswith("{"):
            try:
                event = json.loads(line)
            except ValueError:
                event = None
            if isinstance(event, dict) and "state" in event:
                model = event.get("model")
                where = _relative(str(model).split("::")[0], [job.workspace]) if model else None
                emit({
                    "type": "progress", "entry": entry, "model": where or None,
                    "state": event.get("state"), "phase": event.get("phase"),
                    "progress": event.get("progress"), "elapsed": event.get("elapsed"),
                })
                return True
        if line.endswith("re-run with --verbose for the full traceback"):
            return True  # a flag the sandbox's caller cannot pass
        log(line)
        return False
    return relay


def run_build(job: Job) -> None:
    request = job.request
    # No entries is a files-only build: nothing runs, and what was sent is published.
    entries = [str(entry) for entry in request.get("entry") or []]
    pythonpath = [str(entry) for entry in request.get("pythonpath") or []]
    env = job.env(pythonpath)
    before = scan(job.workspace)
    main_step = None
    for entry in entries:
        script = job.workspace / entry
        if not script.is_file():
            job.fail(f"The entry {entry} is not a file in this build.", file=entry)
            return
        emit({"type": "progress", "entry": entry, "state": "started", "phase": "run"})
        log(f"$ python {entry}")
        step = run_step(
            f"python {entry}", [sys.executable, entry], cwd=job.workspace, env=env, deadline=job.deadline,
            on_stderr=_relay_build_event(job, entry), on_stdout=log,
        )
        job.record(step)
        main_step = step
        if step.timed_out:
            job.fail(job.timeout_message(), kind="timeout", file=entry)
            break
        if step.exit_code != 0:
            error = parse_error(
                step.stderr_lines, [job.workspace], f"python {entry} exited with code {step.exit_code}",
            )
            job.fail(error["message"], file=error["file"] or entry, line=error["line"])
            break
    if main_step is not None:
        job.result["exitCode"] = main_step.exit_code
        job.result["stdout"] = main_step.stdout.text()
        job.result["stderr"] = main_step.stderr.text()
    if job.result["error"] is not None:
        return

    after = scan(job.workspace, hash_limit=job.max_output_bytes) if entries else before
    outputs, dropped = [], []
    for path in changed(before, after):
        (outputs if path.lower().endswith(tuple(OUTPUT_SUFFIXES)) else dropped).append(path)
    total = sum(after[path][0] for path in outputs)
    if len(outputs) > job.max_output_files or total > job.max_output_bytes:
        job.fail(
            f"The build wrote {len(outputs)} files ({total} bytes); a build may keep at most "
            f"{job.max_output_files} files and {job.max_output_bytes} bytes.", kind="limit",
        )
        return
    job.result["outputs"], job.result["dropped"] = outputs, dropped
    for path in dropped:
        log(f"dropped {path}: not a CAD output")
    for path in outputs:
        job.result["files"].append({"path": f"workspace/{path}", "bytes": after[path][0], "sha256": after[path][1]})
    job.result["ok"] = True
    # Every viewable file gets a view, the files that were sent included (a hand-written
    # URDF, a purchased part's STEP), not only what the scripts wrote. Dropped files are
    # never viewable, so the files kept are exactly the inputs plus the outputs.
    viewable = sorted(path for path in after if path.lower().endswith(VIEWABLE) and path not in dropped)
    primary = pick_primary(viewable, entries)
    job.result["primary"] = primary
    if viewable:
        export_dir = job.out / "export"
        args = ["viewer", "export", str(job.workspace), "--out", str(export_dir)]
        for path in viewable:
            args += ["--file", path]
        log("$ cadgen viewer export")
        step = run_step("cadgen viewer export", job.cadgen(*args, "--json"), cwd=job.workspace, env=env,
                        deadline=job.deadline, on_stderr=log)
        job.record(step)
        stderr = step.stderr.text()
        if step.exit_code == 2 and "unknown argument: export" in stderr:
            job.result["exportError"] = "export unavailable"
            log("cadgen viewer export is not available in this cadgen; the build has no viewer export")
        elif step.timed_out:
            job.result["exportError"] = job.timeout_message()
        elif step.exit_code != 0 or not (export_dir / "export.json").is_file():
            job.result["exportError"] = _last_message(step) or f"cadgen viewer export exited with code {step.exit_code}"
        else:
            job.result["export"] = "out/export"
            job.collect(export_dir / "export.json")
            objects = export_dir / "objects"
            if objects.is_dir():
                for path in sorted(objects.iterdir()):
                    if re.fullmatch(r"[0-9a-f]{64}", path.name) and path.is_file() and not path.is_symlink():
                        job.collect(path)

    if primary and request.get("thumbnail", True):
        thumbnail = job.out / "thumbnail.png"
        log(f"$ cadgen snapshot {primary} (thumbnail)")
        step = run_step(
            "cadgen snapshot (thumbnail)",
            job.cadgen("snapshot", primary, str(thumbnail), "--width", "1200", "--height", "630", "--json"),
            cwd=job.workspace, env=env, deadline=min(job.deadline, time.monotonic() + THUMBNAIL_SECONDS),
            on_stderr=log,
        )
        job.record(step)
        if step.exit_code == 0 and thumbnail.is_file():
            job.result["thumbnail"] = "out/thumbnail.png"
            job.collect(thumbnail)
        else:
            log("the thumbnail could not be rendered: " + (_last_message(step) or "no image"))


def _last_message(step: Step) -> str | None:
    """The error a cadgen --json command printed, else its last stderr line."""
    for line in reversed(step.stdout.text().splitlines()):
        if line.startswith("{"):
            try:
                payload = json.loads(line)
            except ValueError:
                continue
            if isinstance(payload, dict) and payload.get("error"):
                return str(payload["error"])[:2000]
    for line in reversed(step.stderr_lines):
        if line.strip() and not line.startswith("{"):
            return line.strip()[:2000]
    return None


def snapshot_args(args: list) -> list[str]:
    """The snapshot flags a request may pass, refused by name otherwise."""
    result: list[str] = []
    items = [str(item) for item in args]
    index = 0
    while index < len(items):
        item = items[index]
        flag, has_inline, _value = item.partition("=")
        if flag in SNAPSHOT_FLAGS_BARE and not has_inline:
            result.append(item)
        elif flag in SNAPSHOT_FLAGS_WITH_VALUE:
            if has_inline:
                result.append(item)
            elif index + 1 < len(items):
                result += [item, items[index + 1]]
                index += 1
            else:
                raise ValueError(f"{flag} needs a value")
        else:
            raise ValueError(f"snapshot argument {item!r} is not allowed")
        index += 1
    return result


def run_snapshot(job: Job) -> None:
    request = job.request
    target = str(request.get("file") or "")
    file_format = str(request.get("format") or "png")
    if file_format not in ("png", "svg"):
        job.fail(f"format must be png or svg, not {file_format!r}", kind="runner")
        return
    if not target or not (job.workspace / target).is_file():
        job.fail(f"{target or 'The snapshot'} is not a file in this build.", kind="runner")
        return
    try:
        extra = snapshot_args(request.get("args") or [])
    except ValueError as exc:
        job.fail(str(exc), kind="runner")
        return
    image = job.out / f"snapshot.{file_format}"
    log(f"$ cadgen snapshot {target}")
    step = run_step(
        "cadgen snapshot", job.cadgen("snapshot", target, str(image), *extra, "--json"),
        cwd=job.workspace, env=job.env(), deadline=job.deadline, on_stderr=log,
    )
    job.record(step)
    job.result["exitCode"] = step.exit_code
    job.result["stdout"], job.result["stderr"] = step.stdout.text(), step.stderr.text()
    if step.timed_out:
        job.fail(job.timeout_message(), kind="timeout")
    elif step.exit_code != 0 or not image.is_file():
        job.fail(_last_message(step) or f"cadgen snapshot exited with code {step.exit_code}")
    else:
        job.result["ok"] = True
        job.result["images"] = [f"out/snapshot.{file_format}"]
        job.collect(image)


def run_inspect(job: Job) -> None:
    request = job.request
    script = job.dir / "inspect.py"
    script.write_text(str(request.get("code") or ""), encoding="utf-8")
    scratch = job.workspace / "tmp"
    before = scan(scratch, skip_tmp=False)
    log("$ python inspect.py")
    # -P keeps the script's own folder off sys.path: a script named inspect.py there
    # would shadow the standard library's inspect module for everything it imports.
    step = run_step(
        "python inspect.py", [sys.executable, "-P", str(script)], cwd=job.workspace,
        env=job.env([str(entry) for entry in request.get("pythonpath") or []]), deadline=job.deadline,
        on_stderr=log, on_stdout=log,
    )
    job.record(step)
    job.result["exitCode"] = step.exit_code
    job.result["stdout"], job.result["stderr"] = step.stdout.text(), step.stderr.text()
    after = scan(scratch, skip_tmp=False)
    images = [path for path in changed(before, after)
              if path.lower().endswith(IMAGE_SUFFIXES) and after[path][0] <= MAX_IMAGE_BYTES]
    for path in images[:MAX_INSPECT_IMAGES]:
        job.result["images"].append(f"workspace/tmp/{path}")
        job.collect(scratch / path)
    if step.timed_out:
        job.fail(job.timeout_message(), kind="timeout")
    elif step.exit_code != 0:
        # The workspace first: a frame in the build's own modules is named as the build
        # names it; the script itself is inspect.py, beside the workspace.
        error = parse_error(
            step.stderr_lines, [job.workspace, job.dir], f"inspect.py exited with code {step.exit_code}",
        )
        job.fail(error["message"], file=error["file"], line=error["line"])
    else:
        job.result["ok"] = True


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        sys.stderr.write("usage: run.py JOB_DIR\n")
        return 2
    job = Job(Path(argv[0]))
    job.out.mkdir(parents=True, exist_ok=True)
    handlers = {"build": run_build, "snapshot": run_snapshot, "inspect": run_inspect}
    try:
        handler = handlers.get(job.kind)
        if handler is None:
            job.fail(f"unknown job kind {job.kind!r}", kind="runner")
        else:
            handler(job)
    except Exception as exc:  # noqa: BLE001 - the result must be written whatever happened
        job.fail(f"the runner failed: {type(exc).__name__}: {exc}", kind="runner")
    job.result["wallMs"] = int((time.monotonic() - job.started) * 1000)
    job.result["flags"]["network"] = (job.flag_dir / "network").exists()
    job.result["log"] = LOG.text()
    target = job.dir / "result.json"
    temporary = job.dir / "result.json.tmp"
    temporary.write_text(json.dumps(job.result, separators=(",", ":")), encoding="utf-8")
    os.replace(temporary, target)
    emit({"type": "done", "ok": job.result["ok"]})
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
