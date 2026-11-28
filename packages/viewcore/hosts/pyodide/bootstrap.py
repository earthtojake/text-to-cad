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
    (``worker._stat``, a memo's file version). Every way ``os`` answers them says the same: by path, by an open
    file, by a name in an open folder (``shutil.rmtree`` tells a folder from a link to one by comparing two of
    them). Only for the real filesystem; a failure is the platform's own, raised as it raises it. What stays the
    platform's: an entry of ``os.scandir`` read without ``os.stat`` (``DirEntry.stat``, ``DirEntry.inode``).

    And two things the platform keeps to itself, which the system must see: the process's mask for the files it
    makes (``os.umask``), and the folder it stands in (``os.chdir``: a worker leaves a project's folder when it is
    idle, so that the folder is not held)."""
    if not host["mounted"]:
        return
    kept = ("/dev/", "/lib/", "/sys/")
    stat, lstat, fstat = os.stat, os.lstat, os.fstat

    def merged(found, facts):
        if isinstance(facts, str):  # gone since, or not the real filesystem's
            return found
        _mode, ino, dev, _links, _uid, _gid, _size, atime, mtime, ctime = (int(fact) for fact in facts)
        cls, (shown, more) = found.__reduce__()
        shown = list(shown)
        shown[1], shown[2] = ino, dev
        shown[7], shown[8], shown[9] = atime // 10**9, mtime // 10**9, ctime // 10**9
        more = dict(more)
        for field, value in (("st_atime", atime), ("st_mtime", mtime), ("st_ctime", ctime)):
            more[field] = value / 1e9
            more[field + "_ns"] = value
        return cls(tuple(shown), more)

    def named(found, path, dir_fd, follow):
        try:
            name = os.fspath(path)
        except TypeError:
            return found
        if isinstance(name, bytes):
            name = os.fsdecode(name)
        if dir_fd is not None and not os.path.isabs(name):
            folder = real["open_path"](dir_fd)
            if folder is None:
                return found
            return merged(found, real["stat"](os.path.join(folder, name), follow))
        name = os.path.abspath(name)
        if name.startswith(kept):
            return found
        return merged(found, real["stat"](name, follow))

    def opened(found, fd):
        return merged(found, real["open_stat"](fd))

    def stat_exact(path, *, dir_fd=None, follow_symlinks=True):
        found = stat(path, dir_fd=dir_fd, follow_symlinks=follow_symlinks)
        return opened(found, path) if isinstance(path, int) else named(found, path, dir_fd, follow_symlinks)

    def lstat_exact(path, *, dir_fd=None):
        return named(lstat(path, dir_fd=dir_fd), path, dir_fd, False)

    def fstat_exact(fd):
        return opened(fstat(fd), fd)

    def umask(mask):
        return int(real["umask"](int(mask)))

    chdir = os.chdir

    def chdir_real(path):
        chdir(path)
        here = os.getcwd()
        if not (here + "/").startswith(kept):
            real["chdir"](here)

    os.stat, os.lstat, os.fstat, os.umask, os.chdir = stat_exact, lstat_exact, fstat_exact, umask, chdir_real


def _sockets(net) -> None:
    """Sockets a program opens to somewhere: the host's (python.mjs), since the platform's own reach nothing
    under Node. ``socket.socket`` is a stream socket that connects -- to a host and port, or to a path
    (``AF_UNIX``) -- sends, receives within its time limit and closes; ``makefile`` is the standard library's
    own over it. What listens, and datagrams, the platform does not have: ``OSError``, said so."""
    import errno
    import socket

    from pyodide.ffi import to_js

    codes = {"ECONNREFUSED": ConnectionRefusedError, "ENOENT": FileNotFoundError, "ECONNRESET": ConnectionResetError,
             "EPIPE": BrokenPipeError, "EACCES": PermissionError, "EPERM": PermissionError, "ETIMEDOUT": TimeoutError}

    def raised(found):
        status, said = int(found[0]), found[1].to_bytes().decode("utf-8", "replace")
        if status == -2:
            raise TimeoutError("timed out")
        kind = codes.get(said, OSError)
        raise kind(getattr(errno, said, errno.EIO), said if kind is OSError else os.strerror(getattr(errno, said, errno.EIO)))

    class HostSocket:
        def __init__(self, family=-1, type=-1, proto=-1, fileno=None):
            self.family = socket.AF_INET if family == -1 else family
            self.type = socket.SOCK_STREAM if type == -1 else type
            self.proto = 0 if proto == -1 else proto
            self._id, self._timeout, self._closed, self._io_refs, self._peer = None, socket.getdefaulttimeout(), False, 0, None
            if fileno is not None or self.type != socket.SOCK_STREAM:
                raise OSError(errno.ENOTSUP, "this Python (WebAssembly) opens stream sockets that connect, and no other")

        def __enter__(self):
            return self

        def __exit__(self, *_error):
            if not self._closed:
                self.close()

        def _open(self):
            if self._id is None:
                raise OSError(errno.ENOTCONN, os.strerror(errno.ENOTCONN))
            return self._id

        def settimeout(self, seconds):
            self._timeout = seconds

        def gettimeout(self):
            return self._timeout

        def setblocking(self, flag):
            self._timeout = None if flag else 0.0

        def getblocking(self):
            return self._timeout != 0.0

        def setsockopt(self, *_given):
            pass

        def getsockopt(self, *_given):
            return 0

        def fileno(self):
            return -1

        def getpeername(self):
            return self._peer

        def getsockname(self):
            return ("0.0.0.0", 0) if self.family != getattr(socket, "AF_UNIX", None) else ""

        def connect(self, address):
            if self.family == getattr(socket, "AF_UNIX", None):
                found = net["connect"](None, None, os.fsdecode(address), self._timeout)
            else:
                found = net["connect"](str(address[0]), int(address[1]), None, self._timeout)
            if int(found[0]) < 0:
                raised(found)
            self._id, self._peer = int(found[0]), address

        def connect_ex(self, address):
            try:
                self.connect(address)
            except OSError as error:
                return error.errno or errno.EIO
            return 0

        def send(self, data, flags=0):
            found = net["send"](self._open(), to_js(bytes(data)))
            if int(found[0]) < 0:
                raised(found)
            return int(found[0])

        def sendall(self, data, flags=0):
            self.send(data)

        def recv(self, size, flags=0):
            found = net["receive"](self._open(), int(size), self._timeout)
            if int(found[0]) < 0:
                raised(found)
            return found[1].to_bytes()

        def recv_into(self, buffer, nbytes=0, flags=0):
            view = memoryview(buffer).cast("B")
            got = self.recv(min(len(view), nbytes or len(view)))
            view[:len(got)] = got
            return len(got)

        def shutdown(self, how):
            pass

        def _decref_socketios(self):
            if self._io_refs > 0:
                self._io_refs -= 1
            if self._closed:
                self.close()

        def close(self):
            self._closed = True
            if self._io_refs <= 0 and self._id is not None:
                held, self._id = self._id, None
                net["close"](held)

        def detach(self):
            raise OSError(errno.ENOTSUP, "this Python's sockets are its host's: none is a descriptor")

        def bind(self, address):
            raise OSError(errno.ENOTSUP, "this Python (WebAssembly) listens on nothing: a socket here connects")

        listen = accept = bind
        makefile = socket.socket.makefile

    def create_connection(address, timeout=socket._GLOBAL_DEFAULT_TIMEOUT, source_address=None, *, all_errors=False):
        made = HostSocket(socket.AF_INET, socket.SOCK_STREAM)
        if timeout is not socket._GLOBAL_DEFAULT_TIMEOUT:
            made.settimeout(timeout)
        made.connect(address)  # the host resolves a name itself
        return made

    if not hasattr(socket, "AF_UNIX"):
        socket.AF_UNIX = 1  # the platform names no path sockets; the host connects to one
    socket.socket, socket.create_connection = HostSocket, create_connection


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
    """``sys.path`` as CPython makes it: the program's folder first (the script's; the working folder for -m, by
    its path, and for -c, as the empty entry) unless it was started safe (-P), then PYTHONPATH, then the standard
    library and the installed packages."""
    named = [entry for entry in os.environ.get("PYTHONPATH", "").split(":") if entry]
    listed = [] if host["isolated"] else named  # -E, -I: the environment's path is not this program's
    first: list[str] = []
    if not host["safe"] and (host["isolated"] or not os.environ.get("PYTHONSAFEPATH")):
        first = [{"script": os.path.dirname(os.path.abspath(host["target"] or "")), "module": os.getcwd()}
                 .get(host["kind"], "")]
    # The interpreter started before the real filesystem was there: it put PYTHONPATH and its own first entry on
    # the path already, and remembered that none of those folders existed.
    rest = [entry for entry in sys.path if entry and entry not in named]
    sys.path[:] = [*first, *listed, *rest]
    sys.path_importer_cache.clear()
    importlib.invalidate_caches()


def _site(host) -> None:
    """What ``site`` does at a Python's start, which this one's ran before the installed packages and the real
    filesystem were there: the packages folder's ``.pth`` files read, then ``sitecustomize`` imported where the
    path holds one. Not with -S."""
    if not host["customize"]:
        return
    import site

    site.addsitedir(host["site"])
    for name in ("sitecustomize", "usercustomize"):
        if name in sys.modules:
            continue
        try:
            importlib.import_module(name)
        except ImportError as error:
            if error.name != name:
                raise


def main(host, real, net) -> int:
    host = host.to_py() if hasattr(host, "to_py") else host
    real = real.to_py(depth=1) if hasattr(real, "to_py") else real
    _sockets(net.to_py(depth=1) if hasattr(net, "to_py") else net)
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
    _site(host)
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
