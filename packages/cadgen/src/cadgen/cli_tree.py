"""The build tree: how a top-level build shows the model graph as its bodies reveal it.

Every model transition — submitted, building (with the phase), current, done, failed —
is an EVENT (``cadgen.daemon.executors.emit_event``). Child builds run in other
processes, so their events travel back to the top-level call through the pool: as
``{"event": ...}`` frames from a daemon worker, as ``CADGEN_EVENT`` stderr lines from a
transient worker. Both arrive here identically, tagged with the root request's id.

Two renderings, chosen once per process:

* a **TTY**: one block on stderr, refreshed in place, one line per model doing WORK.
  Current children are summarized on their parent's line; a finished subtree folds to
  one line, so a 200-model assembly never scrolls. Stdout stays the result channel.
* **non-TTY / ``--json``**: one JSON line per transition on stderr, no drawing.

Nothing here knows what a build is; it renders events.
"""

from __future__ import annotations

import contextlib
import json
import os
import sys
import threading
import time
from pathlib import Path
from typing import Iterator, TextIO

STATE_SUBMITTED = "submitted"
STATE_BUILDING = "building"
STATE_CURRENT = "current"
STATE_DONE = "done"
STATE_FAILED = "failed"
_TERMINAL = {STATE_CURRENT, STATE_DONE, STATE_FAILED}

_REDRAW_INTERVAL = 0.25  # the ticker keeps elapsed times moving while a phase is silent
_NAME_COLUMN = 30  # tree prefix + name, padded so every status starts in one column


def _fmt_seconds(seconds: float) -> str:
    if seconds < 10:
        return f"{seconds:.1f}s"
    if seconds < 600:
        return f"{seconds:.0f}s"
    return f"{seconds / 60:.1f}m"


class _Model:
    __slots__ = (
        "model", "name", "state", "phase", "done", "total", "started", "finished",
        "elapsed", "exit", "parent", "children", "stale", "seen",
    )

    def __init__(self, model: str, parent: str | None) -> None:
        self.model = model
        self.name = Path(model).stem
        self.state = STATE_SUBMITTED
        self.phase = ""
        self.done: int | None = None
        self.total: int | None = None
        self.started = time.monotonic()
        self.finished: float | None = None
        self.elapsed: float | None = None
        self.exit: int | None = None
        self.parent = parent
        self.children: list[str] = []
        self.stale: str | None = None
        self.seen = False  # ever reported by its own process (not just submitted)

    @property
    def terminal(self) -> bool:
        return self.state in _TERMINAL

    def duration(self) -> float:
        if self.elapsed is not None:
            return self.elapsed
        end = self.finished if self.finished is not None else time.monotonic()
        return max(0.0, end - self.started)


class BuildTree:
    """Renders model events for one root request. Thread-safe: events arrive from job
    threads while the body runs on the main thread."""

    def __init__(
        self,
        *,
        root_id: str | None,
        stream: TextIO | None = None,
        json_lines: bool = False,
    ) -> None:
        self._stream = stream if stream is not None else sys.stderr
        self._root_id = root_id
        self._json = bool(json_lines)
        self._tty = (not self._json) and bool(getattr(self._stream, "isatty", lambda: False)())
        self._guard = threading.RLock()
        self._models: dict[str, _Model] = {}
        self._order: list[str] = []
        self._drawn_lines = 0
        self._last_draw = 0.0
        self._closed = False
        self._ticker: threading.Thread | None = None
        self._stop = threading.Event()
        if self._tty:
            self._ticker = threading.Thread(target=self._tick, name="cadgen-build-tree", daemon=True)
            self._ticker.start()

    # --- events ---------------------------------------------------------------------

    def handle(self, event: dict) -> None:
        if not isinstance(event, dict):
            return
        root = event.get("root")
        if self._root_id and root and root != self._root_id:
            return  # someone else's tree
        model = event.get("model")
        state = event.get("state")
        if not isinstance(model, str) or not isinstance(state, str):
            return
        with self._guard:
            if self._closed:
                return
            node = self._models.get(model)
            fresh = node is None
            if node is None:
                parent = event.get("parent") if isinstance(event.get("parent"), str) else None
                node = _Model(model, parent)
                self._models[model] = node
                self._order.append(model)
                if parent is not None:
                    parent_node = self._models.get(parent)
                    if parent_node is None:
                        parent_node = _Model(parent, None)
                        parent_node.state = STATE_BUILDING
                        self._models[parent] = parent_node
                        self._order.insert(0, parent)
                    if model not in parent_node.children:
                        parent_node.children.append(model)
            elif node.parent is None and isinstance(event.get("parent"), str):
                node.parent = event["parent"]
                parent_node = self._models.get(node.parent)
                if parent_node is not None and model not in parent_node.children:
                    parent_node.children.append(model)
            changed = self._apply(node, event, state) or fresh
            if changed:
                if self._json or not self._tty:
                    self._write_line(node)
                else:
                    self._draw(force=True)

    def _apply(self, node: _Model, event: dict, state: str) -> bool:
        """Fold one event into the node; True when anything a reader sees changed."""
        if node.terminal and state in {STATE_SUBMITTED, STATE_BUILDING}:
            return False  # a late event for a finished model
        if node.state in {STATE_DONE, STATE_FAILED} and state == STATE_CURRENT:
            # A second build of a finished model found it current (a diamond: two
            # parents submitted the same child). Its work already shows.
            return False
        before = (node.state, node.phase, node.done, node.total, node.stale)
        if state == STATE_BUILDING:
            if node.state != STATE_BUILDING:
                node.started = time.monotonic()
            node.state = STATE_BUILDING
            node.seen = True
            phase = event.get("phase")
            if isinstance(phase, str):
                node.phase = phase
            done, total = event.get("done"), event.get("total")
            node.done = int(done) if isinstance(done, (int, float)) else None
            node.total = int(total) if isinstance(total, (int, float)) and total else None
        elif state == STATE_SUBMITTED:
            if node.state == STATE_SUBMITTED:
                pass
        elif state in _TERMINAL:
            if node.state == STATE_DONE and state == STATE_DONE and node.finished is not None:
                # A second done (the job thread after the child's own): keep the child's
                # own elapsed, take a stale notice if this one carries it.
                pass
            else:
                node.state = state
                node.finished = time.monotonic()
            elapsed = event.get("elapsed")
            if isinstance(elapsed, (int, float)) and node.elapsed is None:
                node.elapsed = float(elapsed)
            code = event.get("exit")
            if isinstance(code, int):
                node.exit = code
            if state == STATE_FAILED:
                node.state = STATE_FAILED
        stale = event.get("stale")
        if isinstance(stale, str) and stale:
            node.stale = stale
        return before != (node.state, node.phase, node.done, node.total, node.stale)

    # --- JSONL -----------------------------------------------------------------------

    def _write_line(self, node: _Model) -> None:
        payload = {
            "model": node.model,
            "parent": node.parent,
            "state": node.state,
            "phase": node.phase or None,
            "progress": [node.done, node.total] if node.total else None,
            "elapsed": round(node.duration(), 3) if node.state != STATE_SUBMITTED else None,
        }
        if node.stale:
            payload["stale"] = node.stale
        if node.exit is not None and node.state == STATE_FAILED:
            payload["exit"] = node.exit
        with contextlib.suppress(OSError, ValueError):
            self._stream.write(json.dumps(payload, separators=(",", ":")) + "\n")
            self._stream.flush()

    # --- TTY block --------------------------------------------------------------------

    def _roots(self) -> list[_Model]:
        return [self._models[m] for m in self._order if self._models[m].parent is None]

    def _subtree_finished(self, node: _Model) -> bool:
        if not node.terminal:
            return False
        return all(self._subtree_finished(self._models[c]) for c in node.children if c in self._models)

    def _built_below(self, node: _Model) -> int:
        count = 0
        for child in node.children:
            sub = self._models.get(child)
            if sub is None:
                continue
            if sub.state == STATE_DONE:
                count += 1
            count += self._built_below(sub)
        return count

    def _status(self, node: _Model) -> str:
        if node.state == STATE_SUBMITTED:
            return "submitted"
        if node.state == STATE_BUILDING:
            text = "building"
            if node.phase:
                text += f" · {node.phase}"
            if node.total:
                text += f" {node.done or 0}/{node.total}"
            return f"{text}  {_fmt_seconds(node.duration())}"
        if node.state == STATE_CURRENT:
            return "current"
        if node.state == STATE_FAILED:
            return f"✗ failed{f' (exit {node.exit})' if node.exit else ''}"
        text = f"✓ {_fmt_seconds(node.duration())}"
        if node.stale:
            text += f" — already stale: {node.stale}; rerun"
        return text

    def _lines(self, node: _Model, prefix: str, last: bool, top: bool) -> Iterator[str]:
        connector = "" if top else ("└─ " if last else "├─ ")
        children = [self._models[c] for c in node.children if c in self._models]
        current = [c for c in children if c.state == STATE_CURRENT and not c.children]
        work = [c for c in children if c not in current]
        summary = ""
        if current:
            summary = f" ({len(current)} current)"
        collapsed = node.terminal and work and self._subtree_finished(node)
        if collapsed:
            built = self._built_below(node)
            if built:
                summary = f" ({built} built{f', {len(current)} current' if current else ''})"
        label = f"{prefix}{connector}{node.name}"
        yield f"{label:<{_NAME_COLUMN}} {self._status(node)}{summary}"
        if collapsed:
            return
        child_prefix = prefix + ("" if top else ("   " if last else "│  "))
        for index, child in enumerate(work):
            yield from self._lines(child, child_prefix, index == len(work) - 1, False)

    def _render(self) -> list[str]:
        lines: list[str] = []
        for root in self._roots():
            lines.extend(self._lines(root, "", True, True))
        return lines

    def _draw(self, *, force: bool = False) -> None:
        if not self._tty:
            return
        now = time.monotonic()
        if not force and now - self._last_draw < _REDRAW_INTERVAL:
            return
        with self._guard:
            lines = self._render()
            out = []
            if self._drawn_lines:
                out.append(f"\x1b[{self._drawn_lines}F")  # to the start of the block
            for line in lines:
                out.append(f"\x1b[2K{line}\n")
            extra = self._drawn_lines - len(lines)
            if extra > 0:
                out.append("\x1b[2K\n" * extra + f"\x1b[{extra}F")
            with contextlib.suppress(OSError, ValueError):
                self._stream.write("".join(out))
                self._stream.flush()
            self._drawn_lines = len(lines)
            self._last_draw = now

    def _tick(self) -> None:
        while not self._stop.wait(_REDRAW_INTERVAL):
            if any(m.state == STATE_BUILDING for m in list(self._models.values())):
                self._draw()

    def close(self) -> None:
        """Freeze the block: the final tree stays on the terminal as durable lines."""
        with self._guard:
            if self._closed:
                return
            self._closed = True
            self._stop.set()
            if self._tty:
                self._last_draw = 0.0
                self._draw(force=True)
        if self._ticker is not None:
            self._ticker.join(timeout=1.0)


# --- process wiring -----------------------------------------------------------------------


@contextlib.contextmanager
def build_tree(*, json_lines: bool = False, stream: TextIO | None = None) -> Iterator[BuildTree | None]:
    """Own this process's event sink for the length of a top-level build.

    Installs nothing when a sink is already present (a daemon worker relays events as
    frames; a transient worker writes them as ``CADGEN_EVENT`` lines — see
    ``cadgen.daemon.executors``): the tree belongs to the ROOT request only. Mints the
    root id when this process is the root, so every child job inherits it.
    """
    from cadgen.daemon import executors

    if executors.sink_installed() or os.environ.get("CADGEN_EVENTS") == "1":
        yield None
        return
    minted = False
    if not os.environ.get("CADGEN_ROOT_ID"):
        import uuid

        os.environ["CADGEN_ROOT_ID"] = uuid.uuid4().hex
        minted = True
    tree = BuildTree(root_id=os.environ["CADGEN_ROOT_ID"], stream=stream, json_lines=json_lines)
    executors.set_event_sink(tree.handle)
    try:
        yield tree
    finally:
        executors.set_event_sink(None)
        tree.close()
        if minted:
            os.environ.pop("CADGEN_ROOT_ID", None)
