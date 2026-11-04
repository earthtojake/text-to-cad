"""``cad run [uv run's options] SCRIPT.py [ARGS] | -m MODULE [ARGS] | -c CODE | COMMAND [ARGS]`` -- ``uv run``,
with cad pinned at the device's release and the environment made by the device's engine.

It takes ``uv run``'s options and behaves as ``uv run`` does: a script's PEP 723 header (``# /// script``,
its ``dependencies`` and ``requires-python``), ``--with`` (repeated, or a comma-separated list),
``--with-editable``, ``--with-requirements``, ``-m``, ``--python``, the indexes and find-links, a uv project
around the working folder (or ``--project``, ``--no-project``), ``--directory``. An option it does not handle
itself is handed straight to the uv cad-server ships (``uv.find_uv_bin``), which judges it, so ``cad run``
never drifts from uv; an option of uv's that takes a value is read from uv's own list (``VALUED``), and any
is taken as ``--option=value`` too.

cad adds two things:

- **The pin.** The environment holds ``cad[<integrations>]==<device release>`` (or the installation's
  source tree or wheel, ``base.Installation.requirement``). Its integrations are worked out from the
  program's imports (``cad_server._internal.scan``, ``extras.integrations``), or named outright by a header
  that names ``cad[...]``. A bare COMMAND an integration declares (``kicad-cli``: the registry's
  ``commands``) adds that integration, as ``--with cad[<integration>]`` would. A header or project that
  pins cad to another release is refused in one line; an unpinned ``cad`` is given the device's.
- **The environment.** The device's engine makes it, outside any sandbox, over its door, its lines said as
  they come, offline first from uv's cache (``cad_server._internal.extras``, the base for
  ``cad[build123d]`` alone: ``base``); this command, which may run in an agent's sandbox, then runs the
  program with that environment's Python, in the caller's folder and environment, with the program's own
  folder last on its module search path, not first (the library's ``cad._internal.program``): a project's
  ``cad.py`` never stands in for the library. A program whose environment is not the base names its Python
  in its orders, and the engine builds its models in a warm worker of that Python (the own-Python worker
  path, under the worker contract). A COMMAND is the environment's own, never one on PATH; one an
  integration declares runs through the library's module for it (``cad.kicad._command``), in that
  environment's Python, headless in private homes, its arguments, stdio and exit code the tool's.

The ``cad`` command (``cad_server._internal.proxy``) runs this verb with the installation it picks.
"""

from __future__ import annotations

import os
import platform
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

PROG = "cad run"
# The library's runner of a program: ``python ARGS``, the program's folder last on its module search path.
PROGRAM = "cad._internal.program"
USAGE = ("usage: cad run [uv run's options] SCRIPT.py [ARGS...] | -m MODULE [ARGS...] | -c CODE [ARGS...]"
         " | COMMAND [ARGS...]\n")
# uv run's options that take a value (uv 0.13's ``uv run --help``): the rest are flags. One uv adds later that
# takes one is given as ``--option=value``.
VALUED = frozenset({
    "--extra", "--no-extra", "--group", "--no-group", "--only-group", "--no-editable-package", "--env-file",
    "-w", "--with", "--with-editable", "--with-requirements", "--package", "--python-platform", "--index",
    "--default-index", "-i", "--index-url", "--extra-index-url", "-f", "--find-links", "--index-strategy",
    "--keyring-provider", "-P", "--upgrade-package", "--upgrade-group", "--resolution", "--prerelease",
    "--prerelease-package", "--fork-strategy", "--exclude-newer", "--exclude-newer-package",
    "--no-sources-package", "--reinstall-package", "--link-mode", "-C", "--config-setting",
    "--config-settings-package", "--no-build-isolation-package", "--no-build-package", "--no-binary-package",
    "--cache-dir", "--refresh-package", "-p", "--python", "--color", "--allow-insecure-host", "--directory",
    "--project", "--config-file",
})
# Options of uv's that only the making reads: an environment made once is never changed by them, and no key
# holds them.
TRANSIENT = frozenset({"-q", "--quiet", "-v", "--verbose", "--no-progress", "--color", "--offline", "-U", "--upgrade",
                       "-P", "--upgrade-package", "--upgrade-group", "--refresh", "--refresh-package", "--reinstall",
                       "--reinstall-package", "-n", "--no-cache", "--cache-dir"})
# Options of uv's whose value is a path, made absolute against the run's folder before the engine, which
# stands elsewhere, is handed them.
PATHS = frozenset({"-f", "--find-links", "--config-file", "--cache-dir"})
# uv's options for the Python an environment is made on, which ``uv venv`` takes.
PYTHON_OPTIONS = frozenset({"--managed-python", "--no-managed-python", "--no-python-downloads"})
# A project's lock, as uv reads it: ``--locked`` (refused where it is out of date) and ``--frozen`` (as it is).
LOCK_MODES = frozenset({"--locked", "--frozen"})
# A project's own options of what of it is installed: its extras and dependency groups, which a lock's export
# takes (with no lock, uv's pip interface takes the groups, of the project's ``pyproject.toml``).
PROJECT_OPTIONS = frozenset({"--no-extra", "--group", "--no-group", "--only-group", "--all-groups", "--no-dev",
                             "--only-dev", "--no-default-groups", "--package", "--all-packages", "--no-editable",
                             "--no-editable-package"})
# The no-ops: every environment ``cad run`` makes is its own, and never the project's ``.venv``.
NO_OPS = frozenset({"--isolated", "--no-env-file"})
# Each option's long spelling, for a run's options said as one word each (the rebuild command).
LONG = {"-w": "--with", "-i": "--index-url", "-f": "--find-links", "-P": "--upgrade-package", "-C": "--config-setting",
        "-p": "--python", "-q": "--quiet", "-v": "--verbose", "-U": "--upgrade", "-n": "--no-cache"}


class Usage(Exception):
    """A command line ``cad run`` does not read: its usage follows."""


@dataclass
class Plan:
    """A ``cad run`` command line, read (``parse``): what it runs, and what its environment is made of."""

    kind: str = ""  # "script", "module", "code" or "command"
    target: str = ""  # the script's path, the module's name, the code, the command
    args: list[str] = field(default_factory=list)
    with_: list[str] = field(default_factory=list)
    editable: list[str] = field(default_factory=list)
    files: list[str] = field(default_factory=list)
    python: str | None = None
    python_options: list[str] = field(default_factory=list)
    options: list[tuple[str, str | None]] = field(default_factory=list)  # uv's, to hand it, keyed
    transient: list[tuple[str, str | None]] = field(default_factory=list)  # uv's, only the making reads
    directory: str | None = None
    project: str | None = None
    no_project: bool = False
    extras: list[str] = field(default_factory=list)  # a project's extras (``--extra``)
    all_extras: bool = False
    lock_mode: list[str] = field(default_factory=list)  # ``--locked``, ``--frozen``
    project_options: list[tuple[str, str | None]] = field(default_factory=list)  # its groups and the rest
    env_file: list[str] = field(default_factory=list)


def parse(argv: list[str]) -> Plan:
    """``cad run``'s command line (see the module): uv run's options up to what it runs -- a script, ``-m
    MODULE``, ``-c CODE``, ``python ...`` as ``uv run python ...`` takes it, or another command -- and its
    arguments after. ``Usage`` for a line that names nothing to run, or an option with no value."""
    plan = Plan()
    rest = list(argv)
    script_flag = False
    while rest:
        head = rest.pop(0)
        if head == "--":
            break
        if not head.startswith("-") or head == "-":
            rest.insert(0, head)
            break
        if head in ("-m", "--module"):
            if not rest:
                raise Usage("-m takes a module")
            plan.kind, plan.target, plan.args = "module", rest[0], rest[1:]
            return plan
        if head == "-c":
            if not rest:
                raise Usage("-c takes code")
            plan.kind, plan.target, plan.args = "code", rest[0], rest[1:]
            return plan
        if head in ("-s", "--script", "--gui-script"):
            script_flag = True
            continue
        name, has, value = head.partition("=")
        if not has and name.startswith("-") and not name.startswith("--") and len(name) > 2 and name[:2] in VALUED:
            name, value, has = name[:2], name[2:], "="  # ``-pPYTHON``, ``-wpandas``
        if name in VALUED and not has:
            if not rest:
                raise Usage(f"{name} takes a value")
            value = rest.pop(0)
        given = value if (has or name in VALUED) else None
        _option(plan, LONG.get(name, name), given)
    if not rest:
        raise Usage("name a script, -m MODULE, -c CODE or a command")
    if rest[0] in ("-m", "-c") and len(rest) > 1:  # after ``--``
        plan.kind, plan.target, plan.args = {"-m": "module", "-c": "code"}[rest[0]], rest[1], rest[2:]
        return plan
    first, plan.args = rest[0], rest[1:]
    if not script_flag and re.fullmatch(r"python(3(\.\d+)?)?(\.exe)?", first.lower()):
        # ``cad run python SCRIPT``, as ``uv run python SCRIPT``: python's own arguments.
        inner = plan.args
        if inner[:1] == ["-m"] and len(inner) > 1:
            plan.kind, plan.target, plan.args = "module", inner[1], inner[2:]
        elif inner[:1] == ["-c"] and len(inner) > 1:
            plan.kind, plan.target, plan.args = "code", inner[1], inner[2:]
        elif inner and not inner[0].startswith("-"):
            plan.kind, plan.target, plan.args = "script", inner[0], inner[1:]
        else:
            raise Usage("cad run python takes a script, -m MODULE or -c CODE")
        return plan
    if script_flag or first.endswith((".py", ".pyw")) or os.path.isfile(first):
        plan.kind, plan.target = "script", first
    else:
        plan.kind, plan.target = "command", first
    return plan


def _option(plan: Plan, name: str, value: str | None) -> None:
    """One of uv run's options, read into the plan: those cad reads itself, and the rest handed to uv."""
    from cad_server._internal import extras

    if name == "--with":
        named = extras.split(value or "")
        if not named:
            raise extras.Refused("--with takes a requirement: a name, a pin, extras, or a local path or wheel")
        plan.with_ += named
    elif name == "--with-editable":
        plan.editable.append(value or "")
    elif name == "--with-requirements":
        plan.files.append(value or "")
    elif name == "--python":
        plan.python = value
    elif name in PYTHON_OPTIONS:
        plan.python_options.append(name)
    elif name == "--directory":
        plan.directory = value
    elif name == "--project":
        plan.project = value
    elif name == "--no-project":
        plan.no_project = True
    elif name == "--extra":
        plan.extras.append(value or "")
    elif name == "--all-extras":
        plan.all_extras = True
    elif name in LOCK_MODES:
        plan.lock_mode.append(name)
    elif name in PROJECT_OPTIONS:
        plan.project_options.append((name, value))
    elif name == "--env-file":
        plan.env_file.append(value or "")
    elif name in NO_OPS:
        pass
    elif name in TRANSIENT:
        plan.transient.append((name, value))
    else:
        plan.options.append((name, value))


def _words(options: list[tuple[str, str | None]], folder: str) -> tuple[str, ...]:
    """Options as uv is handed them, one word each (``--index-url=https://...``), a path's absolute."""
    from cad_server._internal import extras

    found = []
    for name, value in options:
        if value is None:
            found.append(name)
            continue
        if name in PATHS and not extras._url(value):
            value = extras.absolute(value, folder)
        found.append(f"{name}={value}")
    return tuple(found)


def _env_file(paths: list[str]) -> None:
    """``--env-file``'s variables (``KEY=VALUE`` lines, ``export`` and quotes as dotenv writes them) put in this
    process's environment, which the program runs in, as ``uv run --env-file`` puts them in its."""
    from cad_server._internal import extras

    for path in paths:
        try:
            lines = Path(path).read_text(encoding="utf-8").splitlines()
        except OSError as error:
            raise extras.Refused(f"--env-file {path}: {error.strerror or error}") from None
        for line in lines:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            name, _eq, value = line.removeprefix("export ").partition("=")
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
                value = value[1:-1]
            os.environ[name.strip()] = value


@dataclass
class Prepared:
    """What a plan's environment is made of (``prepare``): its spec, the words that build it again
    (``given``, ``extras.tell``), the script whose header named packages and those it named, and the
    header's ``requires-python``."""

    spec: object
    given: list[str]
    script: str | None
    declared: list[str]
    wanted: str | None


def prepare(plan: Plan, release: str) -> Prepared:
    """The environment a plan runs in, as a spec (``extras.Spec``): its integrations (``extras.integrations``:
    a header's ``cad[...]``, else the program's imports, a project's and ``--with``'s), the header's packages
    -- or, with none, the uv project's --, ``--with``'s and the files and folders it names, uv's options and
    the Python. ``extras.Refused`` in one line for a header that does not read, cad pinned to another release
    than ``release``, or a ``requires-python`` the engine's Python does not meet (with ``--python``, checked
    once the environment is made: ``run``)."""
    from cad._internal.integrations import for_command

    from cad_server._internal import extras, scan

    here = os.getcwd()
    script = Path(plan.target).resolve() if plan.kind == "script" else None
    found = extras.header(script) if script is not None else {}
    named = script.name if script is not None else "the program"
    given_cad: set[str] = set()
    with_: list[str] = []
    for item in plan.with_:
        extra = extras.pinned(item, release, f"--with {item}")
        if extra is None:
            with_.append(extras.normalized(item, here))
        else:
            given_cad.update(extra)
    header_cad: tuple[str, ...] | None = None
    declared: list[str] = []
    folder = str(script.parent) if script is not None else here
    for item in found.get("dependencies") or []:
        extra = extras.pinned(item, release, f"{named}'s header")
        if extra is None:
            declared.append(extras.normalized(item, folder))
        else:
            header_cad = tuple(sorted({*(header_cad or ()), *extra}))
    # A script with a header runs in its own environment, and any project around it is not read: uv run's way.
    project = None
    if not found and not plan.no_project:
        project = extras.project(here, extras.absolute(plan.project, here) if plan.project else None)
    project_cad: set[str] = set()
    editable = [extras.absolute(item, here) for item in plan.editable]
    files = [extras.absolute(item, here) for item in plan.files]
    options = list(_words(plan.options, here))
    lock: str | None = None
    lock_options: list[str] = []
    project_options = list(_words(plan.project_options, here))
    if project is not None:
        where = f"{Path(project.root).name}'s pyproject.toml"
        for item in project.dependencies:
            extra = extras.pinned(item, release, where)
            if extra is not None:
                project_cad.update(extra)
        found_lock = Path(project.root) / "uv.lock"
        if found_lock.is_file():
            # The locked set, exactly, as uv run installs it: exported by uv at the making, its cad refused here
            # when it is another release.
            lock = str(found_lock)
            extras.locked_cad(lock, release)
            lock_options = [*dict.fromkeys(plan.lock_mode), *(f"--extra={extra}" for extra in sorted(set(plan.extras))),
                            *(["--all-extras"] if plan.all_extras else []), *project_options]
        else:
            if plan.lock_mode:
                raise extras.Refused(f"{plan.lock_mode[0]}: {project.root} has no uv.lock to read")
            if project.packaged:
                extra_names = ",".join(sorted(set(plan.extras)))
                editable.append(f"{project.root}[{extra_names}]" if extra_names else project.root)
            else:
                files.append(str(Path(project.root) / "pyproject.toml"))
                options += [f"--extra={extra}" for extra in sorted(set(plan.extras))]
                options += ["--all-extras"] if plan.all_extras else []
            options += project_options  # uv's pip interface reads the project's groups itself
    # Where uv runs, so the uv configuration it reads is the run's (a project's, a uv.toml): the project's
    # folder, else the run's.
    folder = project.root if project is not None else here

    def scanned() -> set[str]:
        # The import roots beside the program's own: its project's, and what ``PYTHONPATH`` names (as the
        # program's run reads it, against the working folder).
        roots = [project.root, str(Path(project.root) / "src")] if project is not None else []
        roots += [extras.absolute(item, here) for item in os.environ.get("PYTHONPATH", "").split(os.pathsep) if item]
        if plan.kind == "script":
            return scan.scan(script=script, roots=roots)
        if plan.kind == "module":
            return scan.scan(module=plan.target, cwd=here, roots=roots)
        if plan.kind == "code":
            return scan.scan(code=plan.target, cwd=here, roots=roots)
        declared = for_command(plan.target)  # a command an integration declares: ``kicad-cli``
        return {declared} if declared is not None else set()

    spec = extras.Spec(
        integrations=extras.integrations(header_cad=header_cad, given_cad=given_cad, project_cad=project_cad,
                                         scanned=scanned, requirements=[*with_, *declared,
                                                                        *(project.dependencies if project else ())]),
        requirements=tuple(sorted(set(with_ + declared))), editable=tuple(dict.fromkeys(editable)),
        files=tuple(dict.fromkeys(files)), options=tuple(options),
        python=(extras.absolute(plan.python, here) if plan.python and ("/" in plan.python or os.sep in plan.python)
                else plan.python),
        python_options=tuple(plan.python_options), environment=extras.uv_settings(),
        config=extras.uv_config(folder), lock=lock, lock_options=tuple(lock_options),
        transient=_words(plan.transient, here), folder=folder)
    # What builds a document of its run again, from any folder: its command line's options, one word each, and
    # its requirements (``extras.tell``).
    again = [*(f"--with-editable={item}" for item in editable if project is None or not item.startswith(project.root)),
             *(f"--with-requirements={item}" for item in files
               if project is None or item != str(Path(project.root) / "pyproject.toml")),
             *([f"--project={project.root}"] if project is not None else []),
             *(f"--extra={extra}" for extra in sorted(set(plan.extras)) if project is not None),
             *(dict.fromkeys(plan.lock_mode) if lock else []),
             *(project_options if lock else []),
             *([f"--python={spec.python}"] if spec.python else []), *plan.python_options, *options,
             *([f"cad[{','.join(sorted(given_cad))}]"] if given_cad else []), *sorted(set(with_))]
    return Prepared(spec, again, str(script) if declared else None, sorted(set(declared)), found.get("requires-python"))


def _admitted(wanted: str | None, version: str, script: str, whose: str) -> None:
    """A header's ``requires-python`` met by the Python ``version`` (``whose``: the server's, the
    environment's), else ``extras.Refused`` in one line."""
    from cad_server._internal import extras

    if not wanted:
        return
    admitted = extras.admits(wanted, version)
    if admitted is None:
        raise extras.Refused(f"{script}'s requires-python, {wanted!r}, is no version specifier")
    if not admitted:
        raise extras.Refused(f"{script} requires Python {wanted}, and {whose} is {version}")


def _command(plan: Plan, python: str) -> list[str] | None:
    """What runs a plan with its environment's ``python``: a script, a module or code through the library's
    runner, the program's folder last on its path (``-P``, then ``PROGRAM``), never first; a command an
    integration declares through the library's module for it (``Integration.runner``), headless; any other
    command the environment's own file of that name. None for a command the environment lacks."""
    from cad._internal.integrations import INTEGRATIONS, for_command

    if plan.kind != "command":
        flag = {"module": ["-m"], "code": ["-c"], "script": []}[plan.kind]
        return [python, "-P", "-m", PROGRAM, *flag, plan.target, *plan.args]
    declared = for_command(plan.target)
    runner = INTEGRATIONS[declared].runner if declared is not None else None
    if runner is not None:
        return [python, "-P", "-m", runner, plan.target, *plan.args]
    folder = Path(python).parent
    found = next((folder / name for name in (plan.target, f"{plan.target}.exe") if (folder / name).is_file()), None)
    return [str(found), *plan.args] if found is not None else None


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args[:1] in (["-h"], ["--help"]):
        sys.stdout.write(USAGE + "\nRun a program as `uv run` does, with cad pinned at this device's release: a "
                                 "script's `# /// script` header names its own packages, and cad's integrations "
                                 "are worked out from its imports (a header naming `cad[...]` decides them); a "
                                 "command an integration declares (`kicad-cli`) gets that integration and runs "
                                 "headless. The environment is made once, by the device's engine, and used again. "
                                 "uv run's options are taken as uv takes them.\n")
        return 0
    from cad_server._internal import base, extras

    def said(line: str) -> None:
        print(f"{PROG}: {line}", file=sys.stderr, flush=True)

    try:
        plan = parse(args)
    except Usage as usage:
        sys.stderr.write(f"{PROG}: {usage}\n{USAGE}")
        return 2
    except base.Refused as refused:
        said(str(refused))
        return 1
    try:
        if plan.directory:
            os.chdir(plan.directory)
        _env_file(plan.env_file)
        installation = base.Installation.here()
        prepared = prepare(plan, installation.release)
        spec = prepared.spec
        script = Path(plan.target).name if plan.kind == "script" else "the program"
        assert isinstance(spec, extras.Spec)
        if spec.python is None:
            _admitted(prepared.wanted, installation.python or platform.python_version(), script, "the server's")
        if spec.default():
            env = base.ensure(installation, told=said, engine=True)
        else:
            env = extras.ensure(installation, spec, told=said, engine=True)
        assert env is not None  # made, or refused
        if spec.python is not None:
            version = str(extras.marker(env).get("python_version") or "")
            if version:
                _admitted(prepared.wanted, version, script, f"the environment's (--python {spec.python})")
    except (base.Refused, OSError) as refused:
        said(str(refused) if isinstance(refused, base.Refused) else f"{refused.strerror or refused}")
        return 1
    extras.tell(prepared.given, prepared.script, prepared.declared)  # what builds a document of it again
    command = _command(plan, env.python)
    if command is None:
        said(f"{plan.target} is no command of its environment: run a script, -m MODULE or -c CODE")
        return 2
    sys.stdout.flush()
    if os.name == "nt":  # no exec on Windows: a child, and its exit code
        import subprocess

        return subprocess.call(command)
    try:
        os.execv(command[0], command)
    except OSError as error:
        print(f"{PROG}: cannot run {command[0]}: {error.strerror or error}", file=sys.stderr, flush=True)
        return 1
    return 1  # not reached


if __name__ == "__main__":
    raise SystemExit(main())
