"""Run a Node builder as a child of the Python process that holds the artifact lock.

The implicit and DXF (3D preview) builders are JavaScript: an ``.implicit.js`` source is an
executable ES module, and the DXF preview mesher is ~3,400 LOC of already-shipped JS. But
**Node cannot hold the coordination lock**. Verified on this repo's interpreter (v22.22.0):
``fs.flock``, ``fs.promises.flock`` and ``O_EXLOCK`` are all absent, and an ``O_EXCL``
lockfile is invisible to :func:`cadgen.coordination.snapshot`, which asks the kernel -- a
reader would report ``idle`` over a live Node build and start a duplicate.

So the split is:

* **Python owns** the lock, the run id, the status record, the freshness re-check and the
  child's lifetime.
* **Node owns** geometry and GLB bytes.

Node reports its progress back over **NDJSON on stdout** (:func:`run_node_builder` below);
everything else it wants to say goes to stderr, which is inherited so it lands in the same
place the Python producer's own diagnostics do.

Two invariants this module exists to hold:

1. **Lock release and child death are coupled.** ``run_node_builder`` kills and reaps the
   child in a ``finally``. A lock outliving its writer -- an orphaned Node process still
   writing into a package no one holds a lock over -- is the single failure mode the whole
   "a thin Python process owns the child" design was chosen to prevent, and is why the
   server request thread was rejected as the lock holder.
2. **Bare specifiers resolve through the exports map.** The published skill runtime ships
   ``packages/implicitjs`` and ``packages/cadjs`` as SOURCE with no ``node_modules``, so the
   child is spawned with ``NODE_PATH=<packages dir>``: a ``NODE_PATH`` entry is treated as a
   ``node_modules`` directory, which makes ``packages/implicitjs`` resolve as the package
   ``implicitjs`` *through its exports map*. A directory ``--alias`` cannot do this -- it
   bypasses the exports map entirely. Same mechanism as
   ``scripts/bundle/skills/bundle-cad.sh:166-167``.

   **Correction to the design doc, measured here:** NODE_PATH alone is NOT sufficient for a
   real ``node`` child. Node's *ESM* resolver ignores NODE_PATH (verified on v22.22.0:
   ``import "implicitjs/glb/progressStream.js"`` throws ERR_MODULE_NOT_FOUND while
   ``require.resolve`` of the same specifier under the same env returns the right file).
   bundle-cad.sh never hit this because esbuild implements NODE_PATH itself. So the child is
   also spawned with ``--import node_resolve_register.mjs``, whose resolve hook forwards a
   bare specifier the ESM resolver could not see to the CJS resolver -- which reads NODE_PATH
   and applies the exports map. Nothing about the exports map is re-implemented.

**stdlib only**, like :mod:`cadgen.coordination` beside which this sits: no OCP, build123d
or ezdxf may be reachable from here.
"""

from __future__ import annotations

import contextlib
import json
import os
import shutil
import subprocess
import sys
import threading
from collections import deque
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

__all__ = [
    "NODE_ENV_VARS",
    "NodeBuilderError",
    "NodeUnavailable",
    "cad_node_executable",
    "node_builder_script",
    "node_package_root",
    "node_child_env",
    "node_resolve_bootstrap",
    "run_node_builder",
]


# Env overrides, in precedence order. ``CADGEN_NODE`` is cadgen's own knob (a PyPI install
# with a Node that is not on PATH); the two ``*_CAD_NODE`` names are what the viewer's
# launchers already set -- ``start-viewer.mjs`` and ``vite.config.mjs`` both assign
# ``env.VIEWER_CAD_NODE = process.execPath``, so a viewer-started build pins the very
# interpreter that launched the viewer instead of whatever PATH happens to resolve to.
NODE_ENV_VARS = ("CADGEN_NODE", "VIEWER_CAD_NODE", "CAD_NODE")

# How long a builder gets to exit on its own after emitting its ``result`` line before it is
# killed. The contract says ``result`` is terminal, so a well-behaved builder exits
# immediately; this only bounds the misbehaving case, and it bounds it rather than hanging.
_EXIT_GRACE_S = 5.0


class NodeUnavailable(RuntimeError):
    """No usable ``node`` binary was found."""


class NodeBuilderError(RuntimeError):
    """A Node builder child failed, or spoke the NDJSON protocol incorrectly."""


def cad_node_executable(repo_root: Path | str | None = None) -> str:
    """Absolute path to the ``node`` binary to spawn builders with.

    Env-first (:data:`NODE_ENV_VARS`), then ``PATH``. ``repo_root`` is accepted for call-site
    symmetry with the other cadgen entrypoints and is not otherwise used -- Node is a
    system/runtime dependency, not a repo-relative one.

    Raises :class:`NodeUnavailable` with an actionable message. This is a soft, CALL-TIME
    dependency: cadgen publishes to PyPI and must not *require* Node, so nothing looks for it
    until a format that needs a JS builder is actually built.
    """
    del repo_root  # accepted for CLI/API parity; Node is not resolved repo-relative
    for name in NODE_ENV_VARS:
        candidate = str(os.environ.get(name) or "").strip()
        if not candidate:
            continue
        resolved = shutil.which(candidate) or (candidate if os.path.isfile(candidate) else None)
        if resolved and os.access(resolved, os.X_OK):
            return str(Path(resolved).resolve())
        raise NodeUnavailable(
            f"{name}={candidate!r} does not point at an executable node binary. "
            f"Unset {name} to fall back to PATH, or set it to a real node executable."
        )

    found = shutil.which("node")
    if found:
        return str(Path(found).resolve())

    raise NodeUnavailable(
        "node was not found on PATH. The implicit and DXF render builders run in Node, and "
        "the packaged CAD Viewer runtime is itself launched by node -- so a missing node "
        "means this environment is broken, not merely unconfigured. Install Node.js (>=20), "
        "or point CADGEN_NODE at an existing node binary."
    )


def node_package_root() -> Path:
    """The ``packages/`` directory this cadgen was loaded from, for ``NODE_PATH``.

    Derived from THIS module's location rather than from a repo root, because it has to be
    right in both layouts: ``packages/cadgen/src/cadgen/_internal/node_runtime.py`` in the
    dev checkout, and ``skills/<skill>/scripts/packages/cadgen/src/cadgen/_internal/...`` in
    a vendored skill runtime. In both, ``parents[4]`` is the ``packages`` dir that also holds
    ``implicitjs`` and ``cadjs``. ``CADGEN_NODE_PACKAGES`` overrides it.
    """
    override = str(os.environ.get("CADGEN_NODE_PACKAGES") or "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return Path(__file__).resolve().parents[4]


def node_builder_script(name: str) -> Path:
    """Absolute path of a builder under ``packages/cadjs/bin``, e.g. ``dxf-artifact.mjs``.

    Derived from :func:`node_package_root` for the same reason it is: the dev checkout and a
    vendored skill runtime lay the ``packages`` dir out differently, and only one of the two
    can be hard-coded. Missing is a PACKAGING failure, not a user error -- a runtime that
    vendors ``cadgen`` but not ``cadjs`` cannot build this format at all -- so it raises with
    the path it looked at rather than degrading to a build that silently writes no preview.
    """
    path = node_package_root() / "cadjs" / "bin" / str(name)
    if not path.is_file():
        raise NodeBuilderError(
            f"Node builder is missing: {path}. The runtime that ships cadgen must also ship "
            "packages/cadjs (and packages/implicitjs, which it imports); set "
            "CADGEN_NODE_PACKAGES to the packages directory that holds them."
        )
    return path


def node_child_env(
    extra: Mapping[str, str] | None = None,
    *,
    package_root: Path | str | None = None,
) -> dict[str, str]:
    """``os.environ`` plus a ``NODE_PATH`` that resolves bare ``implicitjs``/``cadjs``
    specifiers through their exports maps. ``extra`` is overlaid last and wins, including
    over ``NODE_PATH`` -- a caller that knows better is not second-guessed."""
    env = dict(os.environ)
    root = Path(package_root).expanduser().resolve() if package_root else node_package_root()
    existing = [p for p in str(env.get("NODE_PATH") or "").split(os.pathsep) if p]
    entries = [str(root)] + [p for p in existing if p != str(root)]
    env["NODE_PATH"] = os.pathsep.join(entries)
    if extra:
        env.update({str(k): str(v) for k, v in extra.items()})
    return env


def node_resolve_bootstrap() -> str:
    """``file://`` URL of the ``--import`` bootstrap that installs the resolve hook.

    A URL rather than a path so it does not depend on the child's cwd. Ships beside this
    module, so it is present wherever cadgen is -- including every skill runtime that vendors
    ``packages/cadgen`` -- and needs no ``node_modules`` of its own to load.
    """
    path = Path(__file__).resolve().parent / "node_resolve_register.mjs"
    if not path.is_file():  # pragma: no cover - packaging regression
        raise NodeBuilderError(
            f"cadgen's Node resolve bootstrap is missing: {path}. This file must ship with "
            "the package (see [tool.setuptools.package-data] in cadgen's pyproject.toml)."
        )
    # ``Path.as_uri()``, NOT "file://" + pathname2url. On Windows pathname2url already returns a
    # leading ``///`` (nturl2path), so concatenating another ``file://`` produced a five-slash URL
    # that Node rejects outright -- ERR_INVALID_FILE_URL_PATH, before the builder wrote anything
    # (issue #266). POSIX returned ``/usr/...`` from the same call, so the bug was invisible
    # there. as_uri() is correct on both and percent-encodes, which the plugin's own install path
    # needs: it contains a space on Windows.
    return path.as_uri()


def _dispatch(message: Mapping[str, Any], run: Any) -> bool:
    """Apply one protocol message to ``run``. Returns True if it was understood."""
    kind = message.get("type")
    if kind == "phase":
        phase = message.get("phase")
        if not isinstance(phase, str) or not phase:
            return False
        total = message.get("total")
        detail = message.get("detail")
        run.phase(
            phase,
            total=int(total) if isinstance(total, (int, float)) and not isinstance(total, bool) else None,
            detail=str(detail) if isinstance(detail, str) else "",
        )
        return True
    if kind == "total":
        total = message.get("total")
        if isinstance(total, bool) or not isinstance(total, (int, float)):
            return False
        run.set_total(int(total))
        return True
    if kind == "advance":
        count = message.get("n", 1)
        if isinstance(count, bool) or not isinstance(count, (int, float)):
            count = 1
        detail = message.get("detail")
        run.advance(int(count), detail=str(detail) if isinstance(detail, str) else None)
        return True
    if kind == "detail":
        detail = message.get("detail")
        if not isinstance(detail, str):
            return False
        run.detail(detail)
        return True
    return False


# How much of a failing builder's stderr to keep for the raised error. A Node stack trace
# is mostly frames; the first line is the message that names the cause.
NODE_BUILDER_STDERR_TAIL_LINES = 40


def first_builder_error(lines: "deque[str] | list[str]") -> str:
    """The one line worth putting in front of a user.

    Node prints `Error: <message>` and then a stack. The message is the diagnostic; the
    frames are noise in a UI error card. Falls back to the last line when nothing matches,
    so an unusual failure still says something rather than nothing.
    """
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("Error:"):
            return stripped[len("Error:") :].strip()
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("at "):
            return stripped
    return ""


def run_node_builder(
    script: Path | str,
    args: Sequence[str] = (),
    *,
    run: Any,
    cwd: Path | str | None = None,
    env: Mapping[str, str] | None = None,
    node: str | None = None,
    on_message: Callable[[Mapping[str, Any]], None] | None = None,
    stdin_text: str | None = None,
) -> dict[str, Any]:
    """Spawn ``node <script> <args...>``, stream its NDJSON progress into ``run``, and return
    the payload it reported.

    ``run`` is the :class:`~cadgen.coordination.BuildRun` yielded by ``artifact_build`` --
    i.e. the object that is holding the write lock. The child never touches the lock, the run
    id, or the status record; it only describes what it is doing, and this function
    translates that onto the holder.

    **Protocol** -- one JSON object per stdout line:

    ==========================================================  ==================================
    Line                                                        Effect
    ==========================================================  ==================================
    ``{"type":"phase","phase":"sample","total":96|null}``        ``run.phase(phase, total=total)``
    ``{"type":"total","total":973214}``                          ``run.set_total(total)``
    ``{"type":"advance","n":1,"detail":"slice 12/96"}``          ``run.advance(n, detail=detail)``
    ``{"type":"detail","detail":"welding seams"}``               ``run.detail(detail)``
    ``{"type":"result","ok":true,...}``                          becomes the return value
    ==========================================================  ==================================

    Any line that is not a JSON object with a known ``type`` is IGNORED -- same tolerance
    ``cadgen_bridge`` already applies to cold-CLI stdout, so an incidental ``console.log`` from
    a dependency cannot fail a build. Unknown-but-well-formed objects (e.g. a future
    ``{"type":"closure",...}``) are handed to ``on_message`` when one is supplied, and dropped
    otherwise. The returned dict is the ``result`` object with its ``type`` key removed.

    ``result`` is TERMINAL: reading stops there. The child is then given a short grace period
    to exit on its own and killed if it does not, and in every path -- success, protocol
    error, exception raised by ``run``, ``KeyboardInterrupt`` -- a still-live child is killed
    and reaped before this function returns. That coupling is the point: the caller releases
    the lock immediately after, and no Node process may outlive it.

    Raises :class:`NodeBuilderError` on a non-zero exit or a missing ``result`` line, and
    :class:`NodeUnavailable` when no node binary can be found.
    """
    script_path = Path(script).expanduser().resolve()
    if not script_path.is_file():
        raise NodeBuilderError(f"Node builder script does not exist: {script_path}")

    executable = node or cad_node_executable()
    argv = [
        executable,
        "--import",
        node_resolve_bootstrap(),
        str(script_path),
        *[str(a) for a in args],
    ]

    proc = subprocess.Popen(  # noqa: S603 - argv is fully constructed, never shell-parsed
        argv,
        cwd=str(cwd) if cwd is not None else None,
        env=node_child_env(env),
        stdin=subprocess.PIPE if stdin_text is not None else None,
        stdout=subprocess.PIPE,
        # Captured AND echoed, not inherited. Inheriting sent the builder's own diagnostic
        # ("Unsupported DXF entity HATCH") to whatever console the producer happened to own
        # -- which for a viewer build is a server log the user never sees, leaving them with
        # a failure that named no cause. Echoing keeps the live CLI behaviour; capturing is
        # what lets the raised error carry the reason to the UI.
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )

    # Drained on a thread: a builder that fills the stderr pipe while we block reading
    # stdout would deadlock otherwise.
    stderr_tail: deque[str] = deque(maxlen=NODE_BUILDER_STDERR_TAIL_LINES)

    def _drain_stderr() -> None:
        if proc.stderr is None:
            return
        for raw_line in proc.stderr:
            sys.stderr.write(raw_line)
            stripped = raw_line.strip()
            if stripped:
                stderr_tail.append(stripped)

    stderr_thread = threading.Thread(target=_drain_stderr, daemon=True)
    stderr_thread.start()

    # Written on a thread for the same reason stderr is drained on one: a payload larger than
    # the pipe buffer (64 KiB on macOS/Linux) would block here while the child blocks writing
    # progress to a stdout nobody is reading yet. Closing the pipe is what tells the child its
    # input is complete.
    def _write_stdin() -> None:
        try:
            proc.stdin.write(stdin_text)  # type: ignore[union-attr]
        except (BrokenPipeError, ValueError):
            pass  # the child died or closed early; its exit code is the real report
        finally:
            with contextlib.suppress(Exception):
                proc.stdin.close()  # type: ignore[union-attr]

    stdin_thread: threading.Thread | None = None
    if stdin_text is not None:
        stdin_thread = threading.Thread(target=_write_stdin, daemon=True)
        stdin_thread.start()

    result: dict[str, Any] | None = None
    killed_after_result = False
    stdout = proc.stdout
    try:
        for raw in stdout:  # type: ignore[union-attr] - stdout=PIPE above
            line = raw.strip()
            if not line:
                continue
            try:
                message = json.loads(line)
            except (ValueError, TypeError):
                continue  # incidental stdout from the child or a dependency
            if not isinstance(message, dict):
                continue
            if message.get("type") == "result":
                result = {k: v for k, v in message.items() if k != "type"}
                break  # terminal by contract; nothing after it is protocol
            if _dispatch(message, run):
                continue
            if on_message is not None:
                on_message(message)

        if result is None:
            proc.wait()
        else:
            try:
                proc.wait(timeout=_EXIT_GRACE_S)
            except subprocess.TimeoutExpired:
                # It reported its result and then refused to leave. We have what we need and
                # the lock is about to be released, so the child does not get to outlive it.
                proc.kill()
                proc.wait()
                killed_after_result = True
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()
        if proc.stdout is not None:
            proc.stdout.close()
        if proc.stderr is not None:
            proc.stderr.close()

    if stdin_thread is not None:
        stdin_thread.join(timeout=_EXIT_GRACE_S)
    stderr_thread.join(timeout=_EXIT_GRACE_S)
    if not killed_after_result and proc.returncode not in (0, None):
        raise NodeBuilderError(
            f"Node builder failed with exit code {proc.returncode}: {script_path.name}"
            + (f" -- {first_builder_error(stderr_tail)}" if first_builder_error(stderr_tail) else "")
        )
    if result is None:
        raise NodeBuilderError(
            f"Node builder produced no result line: {script_path.name}. It must print exactly "
            'one {"type":"result",...} JSON object on stdout before exiting.'
        )
    return result
