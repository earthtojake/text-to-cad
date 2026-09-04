"""The child that holds the CAD kernel. Nothing else in the server imports OCP.

WHY A CHILD AT ALL, when requirement 3 asks for a DIRECT call
--------------------------------------------------------------
The call IS direct: this process calls cadgen's compile entry point as a Python
function, installs a progress sink on it, and returns its payload dict. What
crosses the process boundary is structured frames, not scraped text — the thing
the old design could not do, because it ran ``cadgen step compile`` as an opaque
CLI child and reverse-scanned stdout for a line starting with ``{``.

What the separate process buys is CRASH ISOLATION. OCCT is C++: a fillet after a
boolean can segfault, and this repo has been bitten by exactly that class. A
segfault in the kernel takes down the process it runs in, and a viewer that dies
because one document is malformed is not a viewer. It also keeps ~280MB of
kernel RSS out of the long-lived server, and keeps cadgen's deliberate
module-eviction (it clears first-party modules between builds for closure
determinism) away from the server's own module space.

THE FRAME CHANNEL IS NOT STDOUT, AND THAT IS LOAD-BEARING
----------------------------------------------------------
OCCT's default messenger writes to FILE DESCRIPTOR 1 from C++, with ANSI colour,
bypassing ``sys.stdout`` entirely. Anything framed on stdout would be
interleaved with kernel chatter mid-build. (The Node backend survived this only
because it reverse-scanned for the LAST line starting with ``{`` — that scan was
the mitigation, not legacy cruft, and a progress frame emitted mid-build has no
such tolerance.)

So: frames go over a loopback socket this process connects back on, and fd 1 is
duplicated onto fd 2 at startup, which sends every byte OCCT prints into the
server's log stream where it belongs. Requests arrive on stdin. Diagnostics and
protocol can then never collide, and EOF on the frame socket stays an unambiguous
crash signal.

Run as: ``python -m cadgen.viewer.compile_worker --frame-port N --token T``
"""

from __future__ import annotations

import json
import os
import socket
import sys
import traceback
import uuid

# The protocol frames, one JSON object per line on the frame socket:
#
#   {"id": <req>, "runId": "...", "progress": {...phase block...}}   zero or more
#   {"id": <req>, "result": {ok, document, package, skipped, contended}}   exactly
#   {"id": <req>, "error": "<message>", "errorType": "...", "traceback": "..."} one of
#
# An exception becomes a VALUE on this channel. No exit-code archaeology, no
# stderr truncation: the parent turns the error string straight into the wire's
# failure shape.
#
# `error` is the exception's BARE message, and the class name rides in the
# separate `errorType` field. The parent prefixes it — "STEP import failed:
# {error}" — and that string is what the viewer's import-failure card shows, so
# a class name spliced into it reads as "STEP import failed: RuntimeError:
# failed to read STEP file" to someone who has no idea what a RuntimeError is.
# cadgen already writes messages meant to be read by a person; a human string
# and a diagnostic label are two fields, never one.

# The document suffixes the import path accepts. cadgen's own CLI doors apply
# the same rule from ``cadgen._internal.doors``; this states it locally rather
# than importing a private module, because the server has ALREADY established
# both of that door's invariants before a request reaches this process:
#
#   * suffix + existence: ``CadgenOps._is_raw_step_file`` (owns_step_path +
#     os.path.exists) gates every call to ``client.compile``.
#   * not a stale GENERATED document: ``resolve_artifact_verdict``'s
#     ``generated`` flag gates the same call, from the sidecar reader.
#
# So the private import bought a re-check of things already checked. The local
# check below keeps the defence.
DOCUMENT_SUFFIXES = (".step", ".stp")


class _FrameChannel:
    """Line-delimited JSON over the loopback socket back to the server."""

    def __init__(self, sock: socket.socket) -> None:
        self._sock = sock

    def send(self, frame: dict) -> None:
        payload = json.dumps(frame, separators=(",", ":"), default=str).encode("utf-8") + b"\n"
        self._sock.sendall(payload)


def _document(document_path: str):
    """The document this request names, or a ``ValueError``/``FileNotFoundError``.

    See ``DOCUMENT_SUFFIXES``: this is deliberately the viewer's own check
    rather than cadgen's private CLI door, because the server has already made
    both of that door's guarantees before spawning us.
    """
    from pathlib import Path

    path = Path(str(document_path)).expanduser()
    if path.suffix.lower() not in DOCUMENT_SUFFIXES:
        accepted = "/".join(DOCUMENT_SUFFIXES)
        raise ValueError(f"the STEP import takes a {accepted} document: {document_path}")
    resolved = path.resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"document does not exist: {document_path}")
    return resolved


def _compile(document_path: str, *, force: bool, request_id, channel: _FrameChannel) -> dict:
    """Call cadgen's compile path directly, narrating it as it goes.

    The kernel-bearing modules are imported HERE, on first use, so a
    spawned-but-unused worker stays small.

    ``build_step_artifact`` rather than the public ``cadgen.step.compile`` verb,
    because that verb hardcodes ``repo_root=Path.cwd()``: os.chdir is
    process-global — unusable under a threading server — and cwd is the wrong
    base anyway, since ``repo_root`` both names the build's display refs and
    bounds the sibling-entry scan. It cannot take a base either: adding one
    would add a ``--base`` flag to ``cadgen step compile`` (its parser is
    MIRRORED from the signature), and a ``sink=`` parameter would disqualify the
    verb from mirror status altogether, since a callable is outside the
    derivable annotation set. ``build_step_artifact`` is the public,
    non-underscored entry point the verb itself calls.
    """
    from pathlib import Path

    from cadgen.step_artifact_cli import build_step_artifact

    # One id for the whole run. The client's bar resets when runId changes,
    # because a ratio is only monotonic within a run — so this must be minted
    # once per request and never per event.
    run_id = uuid.uuid4().hex

    document = _document(document_path)

    def sink(event) -> None:
        channel.send({"id": request_id, "runId": run_id, "progress": event.progress_payload()})

    payload = build_step_artifact(
        # The document's OWN directory, matching what the Node child got from
        # cwd=dirname(candidate). For an imported STEP this reaches
        # _relative_to_base/_cad_ref_for_step, which produce the source_ref and
        # cad_ref display strings — the label the user watches during the build
        # the user watches during the build. Never the served root.
        repo_root=document.parent,
        step=document,
        source_path=None,
        force=force,
        sink=sink,
    )

    def path_of(key: str):
        value = payload.get(key)
        return str(Path(str(value)).resolve()) if value else None

    # The CompileResult shape the wire already carries.
    return {
        "ok": bool(payload.get("ok", True)),
        "document": path_of("stepPath"),
        "package": path_of("packagePath"),
        "skipped": bool(payload.get("skipped")),
        "contended": False,
    }


def _serve(channel: _FrameChannel) -> int:
    # An explicit readline loop rather than iterating the file: this process
    # must act on each request the instant it arrives, and a readline that
    # returns "" is unambiguously the parent closing stdin, which is how a
    # worker learns it has been retired.
    while True:
        line = sys.stdin.readline()
        if not line:
            return 0
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except ValueError:
            continue
        request_id = request.get("id")
        if request.get("op") == "shutdown":
            return 0
        try:
            result = _compile(
                str(request.get("candidate") or ""),
                force=bool(request.get("force")),
                request_id=request_id,
                channel=channel,
            )
            channel.send({"id": request_id, "result": result})
        except BaseException as error:  # noqa: BLE001 - every failure is a frame
            # Including SystemExit/KeyboardInterrupt: a cancelled compile is a
            # failed compile, and the parent is owed an answer either way.
            # str(error) can be empty — `raise RuntimeError()`, or a bare
            # KeyboardInterrupt — and an empty error string would surface as
            # "STEP import failed: ". The class name is the fallback THEN, and
            # only then.
            message = str(error).strip() or type(error).__name__
            channel.send(
                {
                    "id": request_id,
                    "error": message,
                    "errorType": type(error).__name__,
                    "traceback": traceback.format_exc(),
                }
            )


def main(argv: list[str]) -> int:
    port = 0
    token = ""
    index = 0
    while index < len(argv):
        argument = argv[index]
        if argument == "--frame-port" and index + 1 < len(argv):
            index += 1
            port = int(argv[index])
        elif argument == "--token" and index + 1 < len(argv):
            index += 1
            token = argv[index]
        index += 1
    if not port:
        print("compile_worker: --frame-port is required", file=sys.stderr)
        return 2

    sock = socket.create_connection(("127.0.0.1", port))
    channel = _FrameChannel(sock)
    channel.send({"hello": token, "pid": os.getpid()})

    # OCCT prints to fd 1 from C++, so fd 1 must not be a channel anyone parses.
    # Point it at stderr: kernel chatter becomes ordinary log output, and
    # nothing this process writes can corrupt the frame stream.
    try:
        os.dup2(sys.stderr.fileno(), 1)
    except (OSError, ValueError):
        pass

    try:
        return _serve(channel)
    finally:
        try:
            sock.close()
        except OSError:
            pass


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
