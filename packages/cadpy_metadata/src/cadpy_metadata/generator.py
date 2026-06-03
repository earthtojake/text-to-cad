"""Metadata helpers for Python-generated CAD outputs."""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Sequence


TEXT_TO_CAD_PREFIX = "cadpy:"
GENERATION_STATUS_SCHEMA_VERSION = 1
GENERATION_LOCK_SUFFIX = ".generation.lock.json"
GENERATION_STATUS_HEARTBEAT_INTERVAL_SEC = 1.0
_ACTIVE_RUN = threading.local()
@dataclass(frozen=True)
class PythonSourceIdentity:
    source_path: str
    source_hash: str


@dataclass(frozen=True)
class GenerationOutput:
    path: Path
    kind: str


def generation_lock_path(output_path: Path | str, run_id: str) -> Path:
    resolved_output = Path(output_path).expanduser().resolve()
    return resolved_output.parent / f".{resolved_output.name}.{_safe_lock_token(run_id)}{GENERATION_LOCK_SUFFIX}"


def python_source_identity(script_path: Path) -> PythonSourceIdentity:
    resolved_script = script_path.expanduser().resolve()
    repo_root = Path.cwd().resolve()
    return PythonSourceIdentity(
        source_path=_manifest_path(resolved_script, repo_root),
        source_hash=_sha256_file(resolved_script),
    )


def track_generation_run(
    *,
    source_path: Path | None,
    generator: str,
    outputs: Sequence[GenerationOutput | tuple[Path, str] | Path | str],
    repo_root: Path | None = None,
) -> contextlib.AbstractContextManager[None]:
    tracker = _GenerationStatusTracker(
        repo_root=repo_root or Path.cwd(),
        source_path=source_path,
        generator=generator,
        outputs=outputs,
    )
    return tracker.run()


class _GenerationStatusTracker:
    def __init__(
        self,
        *,
        repo_root: Path,
        source_path: Path | None,
        generator: str,
        outputs: Sequence[GenerationOutput | tuple[Path, str] | Path | str],
    ) -> None:
        self.repo_root = repo_root.expanduser().resolve()
        self.source_path = source_path.expanduser().resolve() if source_path is not None else None
        self.generator = str(generator or "").strip()
        self.outputs = tuple(_normalize_generation_output(output) for output in outputs)
        self.run_id = f"{os.getpid()}-{uuid.uuid4().hex}"
        self.status_paths = tuple(
            dict.fromkeys(
                generation_lock_path(output.path, self.run_id)
                for output in self.outputs
                if output.path is not None
            )
        )
        self.status_path = self.status_paths[0] if self.status_paths else None
        self.started_at = _now_iso()
        self.stop = threading.Event()
        self.thread: threading.Thread | None = None

    @contextlib.contextmanager
    def run(self) -> Iterator[None]:
        active_depth = int(getattr(_ACTIVE_RUN, "depth", 0) or 0)
        if active_depth > 0:
            yield
            return

        _ACTIVE_RUN.depth = active_depth + 1
        self._start()
        try:
            yield
        finally:
            try:
                self._finish()
            finally:
                _ACTIVE_RUN.depth = active_depth

    def _start(self) -> None:
        if not self.status_paths:
            return
        self._write_status()
        self.thread = threading.Thread(target=self._heartbeat, daemon=True)
        self.thread.start()

    def _finish(self) -> None:
        self.stop.set()
        if self.thread is not None:
            self.thread.join(timeout=0.25)
        for status_path in self.status_paths:
            try:
                status_path.unlink()
            except FileNotFoundError:
                pass
            except OSError:
                self._write_status(status="finished", status_paths=(status_path,))

    def _heartbeat(self) -> None:
        while not self.stop.wait(GENERATION_STATUS_HEARTBEAT_INTERVAL_SEC):
            self._write_status()

    def _write_status(
        self,
        *,
        status: str = "running",
        status_paths: Sequence[Path] | None = None,
    ) -> None:
        for status_path in tuple(status_paths or self.status_paths):
            try:
                status_path.parent.mkdir(parents=True, exist_ok=True)
                tmp_path = status_path.with_name(f"{status_path.name}.{os.getpid()}.tmp")
                payload = self._status_payload(status=status, status_path=status_path)
                tmp_path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
                tmp_path.replace(status_path)
            except OSError:
                pass

    def _status_payload(self, *, status: str, status_path: Path) -> dict[str, object]:
        base_dir = status_path.parent
        return {
            "schemaVersion": GENERATION_STATUS_SCHEMA_VERSION,
            "id": self.run_id,
            "status": status,
            "pid": os.getpid(),
            "startedAt": self.started_at,
            "updatedAt": _now_iso(),
            "sourcePath": _display_generation_path(self.source_path, base_dir),
            "generator": self.generator,
            "outputs": [
                {
                    "path": _display_generation_path(output.path, base_dir),
                    "kind": output.kind,
                }
                for output in self.outputs
                if output.path is not None
            ],
        }


def xml_with_text_to_cad_metadata(
    xml_text: str,
    identity: PythonSourceIdentity,
    *,
    output_path: Path | None = None,
    source_path: Path | None = None,
) -> str:
    text = _strip_text_to_cad_metadata_comments(str(xml_text or ""))
    metadata_source_path = identity.source_path
    if output_path is not None and source_path is not None:
        metadata_source_path = _display_generation_path(source_path, Path(output_path).expanduser().resolve().parent)
    comment_block = "".join(
        f"<!-- {TEXT_TO_CAD_PREFIX}{key}={value} -->\n"
        for key, value in (
            ("sourcePath", metadata_source_path),
            ("sourceHash", identity.source_hash),
        )
        if value
    )
    declaration = re.match(r"\s*<\?xml[^>]*\?>\s*", text)
    if declaration:
        insert_at = declaration.end()
        return text[:insert_at] + comment_block + text[insert_at:]
    return comment_block + text


def _normalize_generation_output(output: GenerationOutput | tuple[Path, str] | Path | str) -> GenerationOutput:
    if isinstance(output, GenerationOutput):
        return output
    if isinstance(output, tuple):
        output_path, kind = output
        return GenerationOutput(path=Path(output_path), kind=str(kind or "").strip())
    path = Path(output)
    return GenerationOutput(path=path, kind=path.suffix.lower().replace(".", "") or "output")


def _safe_lock_token(value: object) -> str:
    token = "".join(
        character if character.isalnum() or character in {"-", "_"} else "_"
        for character in str(value or "").strip()
    ).strip("._")
    return token or uuid.uuid4().hex


def _display_generation_path(path: Path | None, repo_root: Path) -> str:
    if path is None:
        return ""
    resolved = path.expanduser().resolve()
    return os.path.relpath(resolved, start=repo_root.expanduser().resolve()).replace(os.sep, "/")


def _now_iso() -> str:
    return datetime.fromtimestamp(time.time(), tz=timezone.utc).isoformat().replace("+00:00", "Z")


def _strip_text_to_cad_metadata_comments(xml_text: str) -> str:
    return re.sub(
        r"\s*<!--\s*cadpy:source[A-Za-z]*=[\s\S]*?-->\s*",
        "\n",
        xml_text,
    ).lstrip("\n")


def _manifest_path(path: Path, repo_root: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(repo_root).as_posix()
    except ValueError:
        return resolved.as_posix()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
