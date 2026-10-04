"""Catalog rows computed when a build saves, before a catalog read asks for them.

A build of a STEP the viewer shows replaces the file, and the client reads the
catalog again as soon as the build feed says the build is done. The new file's
row is not cheap: its digest is a read of every byte (the digest names its tree,
``index/document``), and the tree it names must be captured. On a 747-component,
227 MB assembly that is about 110 ms and 90 to 230 ms, and the first read after
the build paid it, between the build's end and the new model on screen.

So the server starts on it when it first hears of the save. The build feed
(``preview.py``) hands on every output a build of the watched file has saved, as
soon as the ledger lists it; a thread here computes each one's row through the
very function a catalog read uses (``scanner.warm_catalog_entry``). A read that
arrives meanwhile joins the computation rather than repeating it: the digest and
the row are each computed once per file version, whoever asks first
(``catalog.artifact_file_hash``, ``scanner._create_step_entry``), and a read of a
file that has changed since asks about the new version, which nothing has
computed yet.

The rows are the file's, as every catalog row is: computed from its bytes. The
tree the ledger says the build saved is used for one thing, starting that tree's
capture while the bytes are read, so the two overlap; whether the row shows that
tree is the bytes' answer.

The file the feed is about goes first: a parent saves last, after its children.
A lazy root (the CAD app's whole filesystem) lists only the files a view names,
so it warms only that one; each view's own feed warms its own file.

Bounded: one warming thread per served root, alive only while it has files to
warm, and one capture beside it; at most :data:`WARM_PENDING_LIMIT` files waiting
(a save beyond that is left to the read that needs it); each file version warmed
once, however often the feed lists its save.

Best effort: warming only saves a read time, so nothing it fails at reaches the
feed. A row it cannot compute, or a thread it cannot start, is left to the read
that asks, which computes and reports it as before; the failure is logged.
"""

from __future__ import annotations

import logging
import os
import threading
from collections import OrderedDict

from .content_types import extension_of
from .scanner import (
    SOURCE_EXTENSIONS,
    catalog_input_fingerprint,
    catalog_lists,
    is_hidden_name,
    node_basename,
    path_is_inside,
    real_path_or,
    relative_path_stays_inside_root,
    warm_catalog_entry,
)

__all__ = ["CatalogWarmer", "WARM_PENDING_LIMIT", "WARM_REMEMBERED_LIMIT"]

LOG = logging.getLogger("cadgen.viewer.warm")

# Saved files waiting to be warmed at once.
WARM_PENDING_LIMIT = 16
# File versions remembered as warmed: the feed lists a finished build's saves on every poll
# for as long as the ledger keeps the build.
WARM_REMEMBERED_LIMIT = 256


class CatalogWarmer:
    """Warms the catalog rows of one served root's saved files, off the request threads."""

    def __init__(self, root_path: str, *, lazy: bool = False) -> None:
        self.root_path = os.path.abspath(root_path)
        self._real_root = real_path_or(self.root_path)
        self._lazy = lazy
        self._lock = threading.Lock()
        self._settled = threading.Condition(self._lock)
        # path -> (its inputs' fingerprint when noted, the tree its build saved)
        self._pending: OrderedDict[str, tuple[tuple, str]] = OrderedDict()
        self._warmed: OrderedDict[str, tuple] = OrderedDict()
        self._working = False

    def saved(self, outputs: dict, watched: str | None = None) -> None:
        """Warm the rows of ``outputs`` (each saved path, as the ledger names it, and the tree
        its build saved), ``watched`` (the file the feed is about) first; a lazy root warms
        only ``watched``. Returns at once: the work is a thread's."""
        first = self._listed(watched) if watched else None
        for output, tree in outputs.items():
            path = self._listed(output)
            if path is None or (self._lazy and path != first):
                continue
            fingerprint = catalog_input_fingerprint(path)
            if fingerprint[1] is None:
                continue  # gone again
            with self._lock:
                if self._warmed.get(path) == fingerprint:
                    continue
                if path not in self._pending and len(self._pending) >= WARM_PENDING_LIMIT:
                    continue
                # A newer save of a file still waiting takes its place.
                self._pending[path] = (fingerprint, str(tree or ""))
                if path == first:
                    self._pending.move_to_end(path, last=False)
        with self._lock:
            # Saves left waiting by a thread that failed are taken up here too.
            start = bool(self._pending) and not self._working
            if start:
                self._working = True
        if start:
            try:
                threading.Thread(target=self._drain, name="cadgen-viewer-catalog-warm", daemon=True).start()
            except RuntimeError as error:  # no thread to be had: the reads compute their rows themselves
                LOG.warning("catalog warm could not start: %r", error)
                with self._lock:
                    self._working = False
                    self._settled.notify_all()

    def wait_settled(self, timeout: float | None = None) -> bool:
        """Whether every noted save has been warmed (within ``timeout`` seconds)."""
        with self._lock:
            return self._settled.wait_for(lambda: not self._working, timeout)

    def _listed(self, output) -> str | None:
        """``output`` spelled as this root's catalog names it, when the catalog lists it."""
        real = real_path_or(os.path.abspath(str(output)))
        try:
            relative = os.path.relpath(real, self._real_root)
        except ValueError:
            return None  # another drive
        if not relative_path_stays_inside_root(relative) or relative == os.curdir:
            return None
        path = os.path.join(self.root_path, relative)
        if self._lazy:
            # A whole filesystem lists what it is asked for, hidden folders included.
            listed = (path_is_inside(path, self.root_path) and not is_hidden_name(node_basename(path))
                      and extension_of(path) in SOURCE_EXTENSIONS)
        else:
            listed = catalog_lists(self.root_path, path)
        return path if listed else None

    def _drain(self) -> None:
        settled = False
        try:
            while True:
                with self._lock:
                    if not self._pending:
                        self._working = False
                        self._settled.notify_all()
                        settled = True
                        return
                    path, (fingerprint, tree) = self._pending.popitem(last=False)
                    # Warmed from now on: the feed lists the save again while it is being warmed.
                    self._warmed[path] = fingerprint
                    self._warmed.move_to_end(path)
                    while len(self._warmed) > WARM_REMEMBERED_LIMIT:
                        self._warmed.popitem(last=False)
                self._warm(path, tree)
        finally:
            if not settled:  # this thread failed: the next save starts another
                with self._lock:
                    self._working = False
                    self._settled.notify_all()

    def _warm(self, path: str, tree: str) -> None:
        capture = None
        try:
            if tree:
                capture = threading.Thread(target=_capture, args=(tree,), name="cadgen-viewer-tree-warm", daemon=True)
                capture.start()
            warm_catalog_entry(self.root_path, path)
        except Exception as error:  # noqa: BLE001 - a row that cannot be computed now is the read's to report
            LOG.warning("catalog warm of %s failed: %r", path, error)
        finally:
            if capture is not None and capture.ident is not None:
                capture.join()


def _capture(tree: str) -> None:
    """Capture the tree a build saved while its file's bytes are read: what fills is the
    capture's own cache, which a row reads only if the bytes name this tree."""
    from cadgen.store.objects import is_object_hash
    from cadgen.store.trees import capture_tree

    if not is_object_hash(tree):
        return
    try:
        capture_tree(tree, retain_payloads=False)
    except Exception as error:  # noqa: BLE001 - a damaged or collected tree is the read's to report
        LOG.debug("tree warm of %s failed: %r", tree[:16], error)
