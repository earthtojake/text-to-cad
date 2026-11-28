"""bootstrap.py: what python.mjs runs first, so the program after it sees the computer as a native Python would.

Each part puts right one thing this platform (CPython on WebAssembly, under Node) rounds, invents or cannot do, and
says which. Nothing here knows cad: the engine's own modules are imported by the program, as on any Python.
"""
from __future__ import annotations

import importlib
import importlib.abc
import importlib.machinery
import os
import sys
import types


def _process(host) -> None:
    """The process's own id: the platform answers 42 for every process, and the engine names a kernel process by
    its id (its ``ready`` frame, its memory)."""
    pid = int(host["pid"])
    os.getpid = lambda: pid


def _files(host, real) -> None:
    """A file's times to the nanosecond and its real inode and device: the platform rounds a time to the
    millisecond and numbers files itself, and the engine tells whether a file is the one a process wrote by those
    (``worker._stat``, a memo's file version). Only for a path of the real filesystem; a failure is the platform's
    own, raised as it raises it."""
    if not host["mounted"]:
        return
    kept = ("/dev/", "/lib/", "/sys/")
    stat, lstat = os.stat, os.lstat

    def exact(found, path, follow):
        try:
            name = os.path.abspath(os.fspath(path))
        except TypeError:
            return found
        if isinstance(name, bytes):
            name = os.fsdecode(name)
        if name.startswith(kept):
            return found
        facts = real(name, follow)
        if isinstance(facts, str):  # gone since, or not the real filesystem's
            return found
        mode, ino, dev, _links, _uid, _gid, _size, atime, mtime, ctime = (int(fact) for fact in facts)
        cls, (shown, more) = found.__reduce__()
        shown = list(shown)
        shown[1], shown[2] = ino, dev
        shown[7], shown[8], shown[9] = atime // 10**9, mtime // 10**9, ctime // 10**9
        more = dict(more)
        for field, value in (("st_atime", atime), ("st_mtime", mtime), ("st_ctime", ctime)):
            more[field] = value / 1e9
            more[field + "_ns"] = value
        return cls(tuple(shown), more)

    def stat_exact(path, *, dir_fd=None, follow_symlinks=True):
        found = stat(path, dir_fd=dir_fd, follow_symlinks=follow_symlinks)
        return found if dir_fd is not None or isinstance(path, int) else exact(found, path, follow_symlinks)

    def lstat_exact(path, *, dir_fd=None):
        found = lstat(path, dir_fd=dir_fd)
        return found if dir_fd is not None else exact(found, path, False)

    os.stat, os.lstat = stat_exact, lstat_exact


# --- imports a program may never use ------------------------------------------------------------------------------
#
# Some packages cost seconds to import here (each of their extension modules is a library the platform links at
# import) and are imported at the top of a module that most programs use little of: a build imports build123d, which
# imports scipy, scikit-learn and IPython, and calls none of them. For the packages the kernel folder names
# (``deferred``), ``import pkg``, ``import pkg.sub`` and ``from pkg.sub import name`` bind a stand-in, and the real
# package is imported the first time one is used: read, called, subclassed, tested against. Then every stand-in
# bound in a module's namespace is replaced by what it stands for, so from that moment the program holds the real
# objects; a stand-in kept elsewhere (a default argument) goes on forwarding to the real one.

_DEFERRED: tuple[str, ...] = ()
_REAL: set[str] = set()
USED: list[str] = []


def _resolve(top: str) -> None:
    if top in _REAL:
        return
    _REAL.add(top)
    USED.append(top)
    held = {name: module for name, module in list(sys.modules.items())
            if isinstance(module, _Module) and (name == top or name.startswith(top + "."))}
    for name in held:
        del sys.modules[name]
    for name in sorted(held):
        importlib.import_module(name)
    # Every stand-in a module bound by an import, now the real thing.
    for module in list(sys.modules.values()):
        space = getattr(module, "__dict__", None)
        if not isinstance(space, dict):
            continue
        for key, value in list(space.items()):
            kind = type(value)
            if kind is _Module and value.__name__.split(".")[0] == top:
                space[key] = sys.modules[value.__name__]
            elif kind is _Name and object.__getattribute__(value, "_module").split(".")[0] == top:
                space[key] = value._real()


class _Name:
    """A name imported from a deferred module (``from scipy.spatial import ConvexHull``): the real one at its
    first use."""

    __slots__ = ("_module", "_name", "_found")

    def __init__(self, module: str, name: str) -> None:
        object.__setattr__(self, "_module", module)
        object.__setattr__(self, "_name", name)
        object.__setattr__(self, "_found", None)

    def _real(self):
        found = object.__getattribute__(self, "_found")
        if found is None:
            module = object.__getattribute__(self, "_module")
            name = object.__getattribute__(self, "_name")
            _resolve(module.split(".")[0])
            try:
                found = getattr(importlib.import_module(module), name)
            except AttributeError:
                found = importlib.import_module(f"{module}.{name}")
            object.__setattr__(self, "_found", found)
        return found

    def __getattr__(self, name):
        return getattr(self._real(), name)

    def __setattr__(self, name, value):
        setattr(self._real(), name, value)

    def __call__(self, *args, **kwargs):
        return self._real()(*args, **kwargs)

    def __mro_entries__(self, bases):
        return (self._real(),)

    def __instancecheck__(self, instance):
        return isinstance(instance, self._real())

    def __subclasscheck__(self, subclass):
        return issubclass(subclass, self._real())

    def __or__(self, other):
        return self._real() | other

    def __ror__(self, other):
        return other | self._real()

    def __getitem__(self, key):
        return self._real()[key]

    def __iter__(self):
        return iter(self._real())

    def __eq__(self, other):
        return self._real() == other

    def __hash__(self):
        return hash(self._real())

    def __repr__(self):
        return repr(self._real())


class _Module(types.ModuleType):
    """A deferred module: any name read from it is a stand-in for the real module's (``_Name``)."""

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        full = f"{self.__name__}.{name}"
        found = sys.modules.get(full)
        return found if found is not None else _Name(self.__name__, name)


class _Finder(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    def find_spec(self, name, path=None, target=None):
        top = name.split(".")[0]
        if top in _DEFERRED and top not in _REAL:
            return importlib.machinery.ModuleSpec(name, self, is_package=True)
        return None

    def create_module(self, spec):
        module = _Module(spec.name)
        module.__path__ = []
        return module

    def exec_module(self, module):
        pass


def _defer(host) -> None:
    global _DEFERRED
    _DEFERRED = tuple(name for name in host["deferred"] if name not in sys.modules)
    if _DEFERRED:
        sys.meta_path.insert(0, _Finder())


# --- the program ---------------------------------------------------------------------------------------------------


def _libraries(host) -> None:
    """Where the platform's loader finds the shared libraries packages bring beside them (``scipy.libs``)."""
    folders = [f"{host['site']}/{name}" for name in host["libraries"]]
    if folders:
        os.environ["LD_LIBRARY_PATH"] = ":".join([*folders, *filter(None, [os.environ.get("LD_LIBRARY_PATH")])])


def _path(host) -> None:
    """``sys.path`` as CPython makes it: the program's folder first (the script's, or the working folder for -m and
    -c) unless it was started safe (-P), then PYTHONPATH, then the standard library and the installed packages."""
    listed = [entry for entry in os.environ.get("PYTHONPATH", "").split(":") if entry]
    first: list[str] = []
    if not host["safe"] and not os.environ.get("PYTHONSAFEPATH"):
        first = [os.path.dirname(os.path.abspath(host["target"]))] if host["kind"] == "script" else [os.getcwd()]
    # The interpreter started before the real filesystem was there: it put PYTHONPATH and its own first entry on
    # the path already, and remembered that none of those folders existed.
    rest = [entry for entry in sys.path if entry and entry not in listed]
    sys.path[:] = [*first, *listed, *rest]
    sys.path_importer_cache.clear()
    importlib.invalidate_caches()


def main(host, real) -> int:
    host = host.to_py() if hasattr(host, "to_py") else host
    _process(host)
    if host["mounted"]:
        os.chdir(host["cwd"])
    _files(host, real)
    _libraries(host)
    sys.executable = host["executable"]
    sys.argv = [host["target"] if host["kind"] == "script" else ("-c" if host["kind"] == "code" else host["target"]),
                *host["argv"]]
    _path(host)
    _defer(host)
    import runpy

    try:
        if host["kind"] == "module":
            sys.argv[0] = host["target"]  # run_module sets it to the module's file
            runpy.run_module(host["target"], run_name="__main__", alter_sys=True)
        elif host["kind"] == "script":
            runpy.run_path(host["target"], run_name="__main__")
        else:
            source = sys.stdin.read() if host["kind"] == "stdin" else host["target"]
            exec(compile(source, "<string>", "exec"), {"__name__": "__main__", "__builtins__": __builtins__})
    except SystemExit as leaving:
        code = leaving.code
        if code is None:
            return 0
        if isinstance(code, int):
            return code
        print(code, file=sys.stderr)
        return 1
    except BaseException:  # noqa: BLE001 - the program's own failure, said as Python says it
        import traceback

        traceback.print_exc()
        return 1
    finally:
        for stream in (sys.stdout, sys.stderr):
            try:
                stream.flush()
            except Exception:  # noqa: BLE001 - a stream already closed
                pass
    return 0
