"""Which release of cad this environment runs: its own, or one cad's update keeps beside it.

cad's update never changes the files of a cad that is installed. It builds each newer release in a folder of its own
(the store: ``cad_server._internal.store``) and then names that folder in one small file in this environment, the
pointer (``POINTER``, in ``sys.prefix``). This module is the other half. The wheel's ``cad.pth`` imports it as the
interpreter starts, before anything of cad's is imported, and where the pointer names a stored release it puts that
folder on the import path in place of this environment's own packages. Every process of the environment -- the
``cad`` command, the server it starts, ``python -m`` -- then runs the stored release, on this environment's
interpreter: ``sys.prefix``, the ``cad`` command and what its installer knows of the environment stay as they are.

The pointer is taken only where all of this holds; anything else leaves the environment running its own packages,
and says nothing:

- it is a pointer of this format (``"pointer": 1``) for this interpreter (``"python"``: its
  ``sys.implementation.cache_tag``);
- it was written for this very install of cad: the file it names in this folder (``"record"``, the ``RECORD`` of the
  cad installed here) has the time and the size it had then (``"stamp"``). Installing cad again, with its installer or
  by hand, writes that file anew, so **a reinstall always runs what it installed**: the way out of a stored release
  that does not run;
- the stored release (``"path"``) is there and whole: its marker (``MARKER``), which the store writes last, opens.

The marker stays open for as long as the process lives (``HELD``). That is how the store tells a release in use from
one it may remove: on Windows a folder with an open file in it cannot be renamed, and elsewhere the open file carries
a shared lock. A release that goes between the pointer's reading and the marker's opening is not taken: the pointer
is read once more.

The standard library alone, nothing of cad's, and never an error. This file is the one part of cad's update that an
update cannot replace -- it runs from the environment the installer made, at the release it installed -- so it knows
as little as it can: no version is compared here, and nothing is decided but whether the pointer is this install's.
What may be pointed at is the update's to decide (``cad_server._internal.auto_update``). What it reads never changes:
the pointer's name, place and the five keys above, the marker's name, and that a stored release is a folder that
works as one entry of the import path, its ``.pth`` files read as an environment's are. It acts only as the
interpreter starts: imported later, under a cad that is already loaded, it changes nothing.
"""

import os
import sys

POINTER = "cad-pointer.json"
MARKER = "cad-store.json"
# This environment's own packages folder; the stored release this process runs in its place, or None; and that
# release's marker, held open for the life of the process.
HERE = os.path.dirname(os.path.abspath(__file__))
STORED = None
HELD = None


def _pointed():
    """The stored release the pointer names for this install of cad, or None. Raises for a pointer it cannot read."""
    try:
        handle = open(os.path.join(sys.prefix, POINTER), encoding="utf-8")
    except OSError:
        return None  # no pointer: an environment that runs its own packages
    import json

    with handle:
        found = json.load(handle)
    if found.get("pointer") != 1 or found.get("python") != sys.implementation.cache_tag:
        return None
    installed = os.stat(os.path.join(HERE, found["record"]))
    if [installed.st_mtime_ns, installed.st_size] != found["stamp"]:
        return None  # cad was installed again since: what was installed runs
    return found["path"]


def _hold(path):
    """The marker of the stored release at ``path``, opened and kept. Raises where the release is not there, or is
    being removed."""
    marker = os.path.join(path, MARKER)
    handle = open(marker, "rb")
    try:
        if os.name != "nt":
            import fcntl

            try:
                fcntl.flock(handle, fcntl.LOCK_SH | fcntl.LOCK_NB)
            except BlockingIOError:
                raise  # the store holds it to remove the release
            except OSError:
                pass  # a file system with no locks: the release runs unmarked
            if not os.path.samestat(os.fstat(handle.fileno()), os.stat(marker)):
                raise OSError("the stored release was removed")
    except BaseException:
        handle.close()
        raise
    return handle


def _take():
    """The stored release the pointer names put in this folder's place on the import path, and held."""
    global STORED, HELD
    if any(name in sys.modules for name in ("cad", "cad_server", "cad_mcp", "cadgen")):
        return  # imported late, by something other than the interpreter's start: never under a cad already loaded
    here = os.path.normcase(HERE)
    at = next((at for at, entry in enumerate(sys.path) if os.path.normcase(os.path.abspath(entry)) == here), None)
    if at is None:
        return  # this folder is not on the import path: nothing of it to replace
    held = None
    for _ in range(2):  # a release removed between the two reads: the pointer names another by now
        path = _pointed()
        if path is None:
            return
        try:
            held = _hold(path)
            break
        except OSError:
            continue
    if held is None:
        return
    sys.path[at] = path
    STORED, HELD = path, held
    import site

    site.addsitedir(path)  # its own .pth files, read as an environment's are


try:
    _take()
except Exception:  # noqa: BLE001 - whatever is wrong with a pointer, the environment runs its own packages
    pass
