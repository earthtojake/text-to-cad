"""A Python environment of its own with a stand-in cad installed, and stand-in releases stored beside it.

What ``_cad_release`` acts on, made small: a real virtual environment (the standard library's ``venv``, no pip) whose
site-packages holds the wheel's own ``_cad_release.py`` and ``cad.pth``, a ``cad-1.0.0.dist-info`` with its ``RECORD``
and ``METADATA``, and tiny ``cad`` and ``cad_server`` packages that say which copy they are (``WHO``); and stored
releases, folders holding the same packages saying ``stored``, their own copy of the two files, a ``.pth`` of their own
and the marker. The pointer is written by hand, key by key, where the rule says it is: the file's format is the
contract, and a test of the reader never borrows the writer.

Each process is started by the environment's own interpreter with nothing of the caller's ``PYTHON*`` variables and
a state folder of the test's (``CAD_STATE_DIR``), so what it runs is what the environment and the pointer say alone.
"""

from __future__ import annotations

import binascii
import json
import os
import shutil
import subprocess
import sys
import venv
from pathlib import Path
from typing import Any

from tests.python.support.paths import LIBRARY

BOOTSTRAP = LIBRARY / "src" / "_cad_release.py"
PTH = LIBRARY / "cad.pth"
INSTALLED, STORED = "1.0.0", "1.0.1"
RECORD = f"cad-{INSTALLED}.dist-info/RECORD"
MARKER = "cad-store.json"
# A key left out of a pointer (``Environment.point``).
LEFT_OUT = object()
# How long a process of the environment may take to start and answer: a bound on a hang, never a wait.
SECONDS = 60

# What a process of the environment says of itself, as JSON on its one line of output.
PROBE = r"""
import json, sys
r = sys.modules.get("_cad_release")
found = {"prefix": sys.prefix, "path": sys.path, "stored": getattr(r, "STORED", None),
         "held": getattr(r, "HELD", None) is not None, "here": getattr(r, "HERE", None)}
try:
    import cad
    found["cad"] = cad.WHO
except ImportError:
    found["cad"] = None
found["lazy"] = getattr(sys.modules.get("cad._internal.lazy_kernel"), "WHO", None)
found["stored_pth"] = "stored_pth_ran" in sys.modules
for name in ("own_only", "stored_only"):
    try:
        __import__(name)
        found[name] = True
    except ImportError:
        found[name] = False
print(json.dumps(found))
"""


def child_environment(state: str | os.PathLike[str] | None, **extra: str) -> dict[str, str]:
    """This process's environment variables less every ``PYTHON*`` one (but one that writes no bytecode) and the
    state folder's, with ``state`` as ``CAD_STATE_DIR`` (None: unset) and ``extra`` on top."""
    dropped = ("CAD_STATE_DIR", "XDG_STATE_HOME", "__PYVENV_LAUNCHER__")
    env = {name: value for name, value in os.environ.items() if not name.startswith("PYTHON") and name not in dropped}
    env["PYTHONDONTWRITEBYTECODE"] = "1"  # what a process imports leaves the folders as they were made
    if state is not None:
        env["CAD_STATE_DIR"] = str(state)
    env.update(extra)
    return env


def pointer_name(prefix: str | os.PathLike[str]) -> str:
    """The pointer's file name for the environment at ``prefix``, by the rule written out here once more:
    ``pointer-<crc32 of its folder, resolved and case-folded as the platform does, 8 hex digits>.json``."""
    folder = os.path.normcase(os.path.realpath(prefix))
    return "pointer-%08x.json" % (binascii.crc32(folder.encode("utf-8", "surrogatepass")) & 0xFFFFFFFF)


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _packages(root: Path, who: str, release: str) -> None:
    """The stand-in ``cad`` and ``cad_server`` at ``root``, saying ``who`` they are, and cad's dist-info of
    ``release``."""
    write(root / "cad" / "__init__.py", f"WHO = {who!r}\n")
    write(root / "cad" / "_internal" / "__init__.py", "")
    write(root / "cad" / "_internal" / "lazy_kernel.py", f"WHO = {who!r}\n")
    write(root / "cad_server" / "__init__.py",
          f"WHO = {who!r}\n__version__ = {release!r}\n\n\ndef main():\n    print('cad_server', WHO)\n    return 0\n")
    write(root / "cad_server" / "__main__.py", "import sys\n\nfrom cad_server import main\n\nsys.exit(main())\n")
    write(root / f"{who}_only.py", "")
    info = root / f"cad-{release}.dist-info"
    write(info / "METADATA", f"Metadata-Version: 2.4\nName: cad\nVersion: {release}\n")
    write(info / "RECORD", "".join(f"{name},,\n" for name in (
        "_cad_release.py", "cad.pth", "cad/__init__.py", "cad_server/__init__.py", f"cad-{release}.dist-info/RECORD")))
    shutil.copyfile(BOOTSTRAP, root / "_cad_release.py")
    shutil.copyfile(PTH, root / "cad.pth")


class _Builder(venv.EnvBuilder):
    def post_setup(self, context: Any) -> None:
        self.python = context.env_exe


class Environment:
    """A virtual environment at ``folder`` with the stand-in cad ``INSTALLED`` in it (``install``)."""

    def __init__(self, folder: Path) -> None:
        builder = _Builder(with_pip=False, symlinks=os.name != "nt")
        builder.create(folder)
        self.python: str = builder.python
        # Asked with ``site`` (``-I``, never ``-S``): it is what makes ``sys.prefix`` the environment's.
        found = subprocess.run([self.python, "-I", "-c", "import importlib.machinery, json, os, sys, sysconfig\n"
                                "suffix = importlib.machinery.EXTENSION_SUFFIXES[0].strip('.').rsplit('.', 1)[0]\n"
                                "machine = os.uname().machine if hasattr(os, 'uname') else ''\n"
                                "print(json.dumps([sys.prefix, sysconfig.get_paths()['purelib'], "
                                "sys.implementation.cache_tag, "
                                "suffix if not machine or machine in suffix else suffix + '-' + machine]))"],
                               capture_output=True, text=True, timeout=SECONDS, env=child_environment(None))
        if found.returncode != 0:
            raise RuntimeError(f"the environment's interpreter did not run: {found.stderr}")
        # ``tag``: what a pointer names its interpreter by; ``built_for``: what a stored release's marker names it by.
        prefix, packages, self.tag, self.built_for = json.loads(found.stdout)
        self.prefix, self.packages = Path(prefix), Path(packages)
        if not (os.path.samefile(self.prefix, folder) and self.packages.is_relative_to(self.prefix)):
            raise RuntimeError(f"{self.python} is not the environment at {folder}: it says {prefix}, {packages}")
        self.install()

    @property
    def record(self) -> Path:
        return self.packages / RECORD

    def install(self) -> None:
        """The stand-in cad installed afresh in the environment's packages folder, its ``RECORD`` written anew."""
        for name in ("cad", "cad_server"):
            shutil.rmtree(self.packages / name, ignore_errors=True)
        _packages(self.packages, "own", INSTALLED)

    def store(self, folder: Path, *, marker: bool = True) -> Path:
        """A stored release of ``STORED`` at ``folder``, made for this environment's interpreter, as ``uv pip install
        --target`` and the store leave one: the packages, the two files at the root, a ``.pth`` of its own (it puts a
        module in ``sys.modules``), and, unless ``marker`` is false, the marker, written last."""
        _packages(folder, "stored", STORED)
        write(folder / "zz-stored.pth",
              "import sys, types; sys.modules['stored_pth_ran'] = types.ModuleType('stored_pth_ran')\n")
        if marker:
            write(folder / MARKER, json.dumps({"store": 1, "release": STORED, "python": self.tag,
                                               "for": self.built_for, "built": 0}))
        return folder

    def pointer_path(self, state: str | os.PathLike[str], prefix: str | os.PathLike[str] | None = None) -> Path:
        """Where the environment's pointer is in the state folder ``state``: ``store/<pointer_name>``."""
        return Path(state) / "store" / pointer_name(self.prefix if prefix is None else prefix)

    def keys(self, stored: Path, **changes: Any) -> dict[str, Any]:
        """A pointer to ``stored`` for the cad installed now, key by key, with ``changes`` (``LEFT_OUT``: a key
        left out)."""
        stamp = self.record.stat()
        keys: dict[str, Any] = {"pointer": 1, "python": self.tag, "prefix": os.path.normcase(os.path.realpath(self.prefix)),
                                "record": RECORD, "stamp": [stamp.st_mtime_ns, stamp.st_size], "path": str(stored)}
        keys.update(changes)
        return {name: value for name, value in keys.items() if value is not LEFT_OUT}

    def point(self, state: str | os.PathLike[str], stored: Path, **changes: Any) -> dict[str, Any]:
        """The pointer to ``stored`` written by hand into the state folder ``state`` (``keys``)."""
        keys = self.keys(stored, **changes)
        write(self.pointer_path(state), json.dumps(keys))
        return keys

    def run(self, *arguments: str, state: str | os.PathLike[str] | None, python: str | None = None,
            env: dict[str, str] | None = None, cwd: str | os.PathLike[str] | None = None) -> subprocess.CompletedProcess:
        """The environment's interpreter (or ``python``) run with ``arguments``, its state folder ``state``."""
        return subprocess.run([python or self.python, *arguments], capture_output=True, text=True, timeout=SECONDS,
                              env=env if env is not None else child_environment(state), cwd=cwd or self.prefix)

    def probe(self, *flags: str, state: str | os.PathLike[str] | None, **options: Any) -> dict[str, Any]:
        """What a process of the environment started with ``flags`` says of itself (``PROBE``). It must end well
        and print nothing on its standard error."""
        found = self.run(*flags, "-c", PROBE, state=state, **options)
        if found.returncode != 0 or found.stderr:
            raise AssertionError(f"exit {found.returncode}: {found.stderr}")
        return json.loads(found.stdout)
