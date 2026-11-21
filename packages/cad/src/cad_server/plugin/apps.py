"""The agent apps: ``APPS``, the one table of them, and what a run does in each (``install_apps``).

A row says how the app is found, how ours is installed and updated (from GitHub, and from a local folder for a
checkout's development install), and how our old copies there are found and removed. A correction is one row. Each
row's comment says how its commands were checked: by the vendor's documentation (its address), by the CLI's own
``--help``, by superpowers' practice, or not at all.

For every app found, in the table's order: ours in -- the plugin installed or updated with that app's own command,
from the GitHub repository's ``latest`` branch, or the skills copied into the agent's own skills folder --, and only
then what earlier releases left there out (each row, Claude Desktop's server, and the loose copies of our skills:
``remove_loose_skills``): the new copy is in place before an old one goes, so a failed download or a GitHub outage
leaves every app with what it had. One app failing, even with an error no row foresaw, never stops the others; a
failure carries a word for why, chosen where it failed (``Outcome.reason``). One line is said per app as it
finishes.

The standard library alone.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from . import computer
from .computer import (EXCEPTION, Failed, Here, Ran, copy_tree, discard, read_json, read_toml, same_path, swap, table,
                       version_key, within)
from .source import (BRANCH, COPY_MARK, DEV_CATALOG, DEV_MARK, OUR_CATALOGS, OUR_PLUGINS, PLUGIN, REPOSITORY,
                     RETIRED_SKILLS, SKILLS, URL, Source, our_folder, our_repository, our_skill)
from .terminal import Live

# The CLI the Codex app bundles (macOS).
CODEX_BUNDLED = "/Applications/ChatGPT.app/Contents/Resources/codex-cli/bin/codex"
# What Codex checks out of the `latest` branch (`marketplace add --sparse`): the catalog, Codex's manifest and what it
# names (its logo, the skills, the server line), the files at the branch's root coming with them. Without it, Codex
# clones the whole repository, every commit of every branch (over 400 MB), as it adds the catalog and again at every
# `marketplace upgrade`, which gives that clone 30 seconds (0.171.0): too few on a Windows computer (measured: 47 s
# on Windows Server 2022, 25 s on a fast Linux one), where the upgrade, and so every update, failed. Sparse, the add
# and the upgrade take 2 to 3 seconds and keep 19 MB. A file the Codex manifest comes to name outside these is added
# here (``tests/python/global/test_plugin_manifests.py`` checks it).
CODEX_SPARSE = (".claude-plugin", ".codex-plugin", "skills", "codex.mcp.json")


# --- the apps -----------------------------------------------------------------------------------------


@dataclass
class Context:
    """What one run knows as it goes: the source, and whether Claude Code now has our plugin (Cursor and Grok Build
    load Claude Code's plugins, so they then need none of their own)."""

    source: Source
    claude_has_ours: bool = False
    claude_found: bool = False


@dataclass
class Outcome:
    status: str  # installed, updated, removed, skipped, failed; or note: the words alone, nothing done
    words: str = ""
    removed: List[str] = field(default_factory=list)
    has_ours: Optional[bool] = None  # whether the app now has our plugin; by default, installed or updated
    reason: str = ""  # failed: why, in a word chosen where it failed (``computer.REASONS``), never its message

    @property
    def ours(self) -> bool:
        return self.has_ours if self.has_ours is not None else self.status in ("installed", "updated")

    def line(self, name: str) -> str:
        if self.status == "note":
            return f"{name}: {self.words}"
        text = f"{name}: {self.status}" + (f": {self.words}" if self.words else "")
        if self.removed:
            text += f" (removed old copies: {', '.join(self.removed)})"
        return text


NOT_FOUND = Outcome("skipped", "not found")
QUIET = Outcome("skipped")  # nothing to do and nothing worth a line (Claude Desktop with nothing of ours)


def fill(templates: Sequence[Sequence[str]], source: Source, here: Optional[Here] = None) -> List[List[str]]:
    """The templates with their words filled in; ``{fetched}``, the ``latest`` branch fetched (``Source.root``), only
    where a template names it."""
    words = source.words()
    if here is not None and any("{fetched}" in part for argv in templates for part in argv):
        words["fetched"] = str(source.root(here))
    return [[part.format(**words) for part in argv] for argv in templates]


@dataclass
class App:
    """One row of the table. ``command``: the CLI the app is found by and run with. ``install`` and ``update``:
    its commands for a GitHub copy, ``local`` for a checkout's folder (a development install), with ``{repo}``,
    ``{url}``, ``{branch}``, ``{plugin}``, ``{catalog}`` and ``{folder}`` filled in. ``installed``: whether ours is there
    already; without it, ``update`` runs first and ``install`` where that fails. ``handler``: an app whose old
    copies need more than its commands (Claude Code, Codex, Cursor, Gemini CLI, Grok Build, Claude Desktop,
    Hermes Agent, Antigravity), or whose commands depend on what it holds already (GitHub Copilot CLI).
    ``folder``: an agent with no plugin command, given the skills in its own folder; ``marks`` find it.
    ``signed_out``: an app that takes a plugin only from a person signed in to it says so in these words; where it does,
    the app is skipped with what it said, not failed (``plugin_command``): nothing a run can do changes it, and a run
    again changes nothing until the person signs in."""

    key: str
    name: str
    command: Optional[str] = None
    install: Sequence[Sequence[str]] = ()
    update: Sequence[Sequence[str]] = ()
    local: Sequence[Sequence[str]] = ()
    installed: Optional[Callable[[Here], bool]] = None
    handler: Optional[Callable[["App", Here, Context], Outcome]] = None
    folder: Optional[Callable[[Here], Path]] = None
    marks: Optional[Callable[[Here], List[Path]]] = None
    signed_out: str = ""  # what the app's command says where nobody is signed in to it (a pattern, any case)

    def run(self, here: Here, context: Context) -> Outcome:
        if self.handler is not None:
            return self.handler(self, here, context)
        if self.folder is not None:
            return copy_skills(self, here, context)
        return plugin_command(self, here, context)


def plugin_command(app: App, here: Here, context: Context) -> Outcome:
    """An app installed and updated by its own commands alone (nothing of ours is removed)."""
    cli = here.which(app.command or "")
    if not cli:
        return NOT_FOUND
    source = context.source
    if source.local:
        if not app.local:
            return Outcome("skipped", "no install from a local folder")
        for argv in fill(app.local, source, here):
            here.must([cli, *argv])
        return Outcome("installed", f"from {source.folder}")
    update = fill(app.update, source, here)

    def run_all(commands: List[List[str]]) -> Optional[Ran]:
        for argv in commands:
            ran = here.run([cli, *argv])
            if not ran.ok:
                return ran
        return None

    def give_up(failed: Ran) -> Outcome:
        if app.signed_out and re.search(app.signed_out, failed.out, re.IGNORECASE):
            return Outcome("skipped", f"nobody is signed in to it ({failed.last()})")
        raise Failed(failed.last(), failed.reason)

    known = app.installed(here) if app.installed is not None else None
    if known and update:
        failed = run_all(update)
        if failed is None:
            return Outcome("updated")
        return give_up(failed)
    if known is None and update and run_all(update) is None:
        return Outcome("updated")
    install = fill(app.install, source, here)
    failed = run_all(install)
    if failed is None:
        return Outcome("installed")
    if app.installed is not None and app.installed(here):
        return Outcome("installed", f"its command said: {failed.last()}")
    return give_up(failed)


# Claude Code and Codex: a plugin is name@catalog. Ours from GitHub is text-to-cad@earthtojake, from the repository's
# `latest`. Earlier: cad@text-to-cad (0.5.0-0.7.5, the catalog then named text-to-cad, on GitHub), cad@earthtojake
# (0.7.6), text-to-cad@text-to-cad (0.10.0-0.11.11's installer: a local catalog at <state>/plugin), and a checkout's
# text-to-cad@earthtojake-dev.


@dataclass
class Catalog:
    name: str
    kind: str  # github, git, directory, other
    where: str = ""  # the repository or the folder
    ref: str = ""
    sparse: Tuple[str, ...] = ()  # the paths a git copy checks out, where it checks out a few (Codex's ``--sparse``)

    def ours(self, here: Here) -> bool:
        if self.name == DEV_CATALOG:
            return True
        if self.kind in ("github", "git"):
            return our_repository(self.where)
        if self.kind == "directory":
            return our_folder(here, self.where)
        return False

    def matches(self, here: Here, source: Source, sparse: Sequence[str] = ()) -> bool:
        """Whether it is the catalog the source installs from, as the source would add it (``sparse``: the paths a
        git copy of it checks out, none for all)."""
        if source.local:
            return self.kind == "directory" and same_path(self.where, source.folder)
        return (self.kind in ("github", "git") and our_repository(self.where) and self.ref == BRANCH
                and tuple(self.sparse) == tuple(sparse))


def marketplace_app(app: App, here: Here, context: Context, cli: Optional[str], catalogs: Dict[str, Catalog],
                    plugins: Sequence[str], verbs: Dict[str, Any], sparse: Sequence[str] = ()) -> Outcome:
    """Claude Code's and Codex's flow. First ours is put in: the source's catalog added (or brought up to date) and
    our plugin installed (or updated) from it. Only once that worked do our other catalogs and plugins go. Where a
    catalog of ours under the source's name points elsewhere (``main``, a checkout) it must be replaced: GitHub is
    checked first, and if the new one cannot be added and installed, the old one is put back. ``verbs``: the app's
    commands, by what they do; ``verbs["readd"]`` makes the command that adds a recorded catalog again. ``sparse``: the
    paths the app's copy of a GitHub catalog checks out (none: all); one of ours that checks out others is replaced."""
    if not cli:
        return NOT_FOUND
    source = context.source
    target = source.catalog
    ours = f"{PLUGIN}@{target}"
    words = source.words()

    def do(key: str) -> None:
        for argv in verbs[key]:
            here.must([cli, *[part.format(**words) for part in argv]])

    def ids(name: str) -> List[str]:
        return [plugin for plugin in plugins if plugin.endswith(f"@{name}") and plugin.split("@")[0] in OUR_PLUGINS]

    present = catalogs.get(target)
    if present is not None and not present.ours(here):
        raise Failed(f"the {target} catalog is another source's ({present.where or present.kind}): left alone")
    replaced = False
    if present is not None and present.matches(here, source, sparse):
        do("refresh")
        do("update" if ours in plugins else "install")
        status = "updated" if ours in plugins else "installed"
    elif present is not None:
        # Ours, from another source: replaced, and put back if the new one does not go in.
        source.reachable(here)
        had = ours in plugins
        for plugin in ids(target):
            here.must([cli, *verbs["remove"][0], plugin])
        here.must([cli, *verbs["forget"][0], target])
        replaced = True
        try:
            do("add_local" if source.local else "add")
            do("install")
        except Failed as error:
            try:
                here.must([cli, *verbs["readd"](present)])
                if had:
                    here.must([cli, *[part.format(**words) for part in verbs["install"][0]]])
                back = "the earlier copy was put back"
            except Failed as again:
                back = f"the earlier copy could not be put back ({again}): run this again"
            raise Failed(f"{error}; {back}", error.reason) from error
        status = "updated" if had else "installed"
    else:
        do("add_local" if source.local else "add")
        do("install")
        status = "installed"
    # Ours is in: now our other copies go. One that cannot be removed is said, and ours stays installed.
    removed, notes = [], []
    for name in OUR_CATALOGS:
        catalog = catalogs.get(name)
        found = ids(name)
        if name == target:
            for plugin in ([] if replaced else [plugin for plugin in found if plugin != ours]):
                try:
                    here.must([cli, *verbs["remove"][0], plugin])
                    removed.append(plugin)
                except Failed as error:
                    notes.append(f"{plugin} stays ({error})")
            continue
        if catalog is not None and not catalog.ours(here):
            if found:
                notes.append(f"{', '.join(found)} left alone: the {name} catalog is another source's "
                             f"({catalog.where or catalog.kind})")
            continue
        try:
            for plugin in found:
                here.must([cli, *verbs["remove"][0], plugin])
                removed.append(plugin)
            if catalog is not None:
                here.must([cli, *verbs["forget"][0], name])
        except Failed as error:
            notes.append(f"the {name} catalog stays ({error})")
    return Outcome(status, "; ".join(notes), removed)


def claude_dir(here: Here) -> Path:
    return Path(here.environ.get("CLAUDE_CONFIG_DIR") or here.home / ".claude")


def claude_code(app: App, here: Here, context: Context) -> Outcome:
    """Claude Code, from its records (``plugins/installed_plugins.json``, ``plugins/known_marketplaces.json``):
    only the user scope's plugins are ours to change; a project's, an administrator's, and claude.ai's synced
    copies are left. Its command is ``claude``, and only that: never the private copy another app (Claude Desktop)
    keeps for itself. Verified: `claude plugin --help` and its subcommands
    (2.1.316, 2.1.325: `marketplace remove --scope user`); docs https://code.claude.com/docs/en/discover-plugins
    (`owner/repo#ref` pins a branch; `marketplace remove` uninstalls its plugins; `plugin update
    <plugin>@<marketplace>`)."""
    cli = here.which("claude")
    context.claude_found = bool(cli)
    folder = claude_dir(here) / "plugins"
    recorded = table(read_json(folder / "installed_plugins.json"))
    plugins = [name for name, entries in table(recorded.get("plugins")).items()
               if any((entry.get("scope") or "user") == "user"
                      for entry in (entries if isinstance(entries, list) else [entries]) if isinstance(entry, dict))]
    catalogs = {}
    for name, entry in table(read_json(folder / "known_marketplaces.json")).items():
        source = table(entry).get("source")
        if not isinstance(source, dict):
            continue
        kind = source.get("source")
        where = source.get("path") if kind == "directory" else source.get("repo") or source.get("url") or ""
        catalogs[name] = Catalog(name, kind if kind in ("github", "git", "directory") else "other", str(where or ""),
                                 str(source.get("ref") or ""))

    def readd(catalog: Catalog) -> List[str]:
        place = catalog.where + (f"#{catalog.ref}" if catalog.ref and catalog.kind != "directory" else "")
        return ["plugin", "marketplace", "add", place]

    verbs = {
        "remove": [["plugin", "uninstall"]],
        "forget": [["plugin", "marketplace", "remove", "--scope", "user"]],
        "add": [["plugin", "marketplace", "add", "{repo}#{branch}"]],
        "add_local": [["plugin", "marketplace", "add", "{folder}"]],
        "refresh": [["plugin", "marketplace", "update", "{catalog}"]],
        "install": [["plugin", "install", "{plugin}@{catalog}"]],
        "update": [["plugin", "update", "{plugin}@{catalog}"]],
        "readd": readd,
    }
    outcome = marketplace_app(app, here, context, cli, catalogs, plugins, verbs)
    context.claude_has_ours = outcome.ours
    return outcome


def _codex_version(path: str, here: Here) -> Tuple[int, ...]:
    """A ``codex`` command's version: from the metadata its package keeps beside it (the app's bundle's
    ``codex-package.json``, the npm package's ``package.json``), else asked of the command, with ``CODEX_HOME`` a
    folder thrown away after (Codex writes into it as it starts, even for ``--version``). As 0.11.10 did."""
    real = Path(os.path.realpath(path))
    for manifest, (key, value) in ((Path(path).parent.parent / "codex-package.json", ("variant", "codex")),
                                   (real.parent.parent / "package.json", ("name", "@openai/codex"))):
        data = table(read_json(manifest))
        if data.get(key) == value and version_key(data.get("version")):
            return version_key(data["version"])
    thrown_away = tempfile.mkdtemp(prefix="cad-codex-home-")
    try:
        ran = here.run([path, "--version"], timeout=60, environ={"CODEX_HOME": thrown_away})
    finally:
        shutil.rmtree(thrown_away, ignore_errors=True)
    words = ran.out.split()
    return version_key(words[-1]) if ran.ok and words else ()


def codex_cli(here: Here) -> Optional[str]:
    """``CODEX_CLI``, else the newer of the ``codex`` on PATH and the one the Codex app bundles (macOS), as 0.11.10
    chose: both write the ``~/.codex`` the app, the CLI and the IDE extension share, so an install must come from a
    CLI at least as new as the app that reads it."""
    named = here.environ.get("CODEX_CLI")
    if named:
        return here.which(named)
    candidates = [here.which("codex")]
    if here.platform == "darwin" and not here.path_only:
        candidates.append(CODEX_BUNDLED)
    found = list(dict.fromkeys(path for path in candidates if path and os.access(path, os.X_OK)))
    if len(found) < 2:
        return found[0] if found else None
    versions = {path: _codex_version(path, here) for path in found}
    return max(found, key=lambda path: versions[path])


def codex(app: App, here: Here, context: Context) -> Outcome:
    """Codex, from its config (``$CODEX_HOME/config.toml``: ``[marketplaces.<name>]`` with ``source_type``,
    ``source``, ``ref`` and ``sparse_paths``; ``[plugins."<id>"]``). A copy from OpenAI's directory (``openai-*``) is
    left. Our GitHub catalog checks out ``CODEX_SPARSE`` alone; one added before it did (a whole clone, whose upgrade
    fails on a slow disk) is replaced. Verified: `codex plugin --help` and its subcommands (0.169: `marketplace add
    <owner/repo> --ref`, `marketplace upgrade`, `add`, `remove`; 0.171: `--sparse`, there in 0.139 already, which
    finds no plugin in our catalog with or without it), and the commands run (0.149.1,
    0.169.0 and 0.171.0 on Linux, 0.171.0 on Windows, no one signed in); docs
    https://developers.openai.com/codex/plugins/build (`--ref`, `upgrade`). `add` again after `upgrade` copies the
    plugin again: Codex keeps a copy, and the docs do not say an upgrade refreshes it."""
    config = read_toml(Path(here.environ.get("CODEX_HOME") or here.home / ".codex") / "config.toml")
    plugins = list(table(config.get("plugins")).keys())
    catalogs = {}
    for name, entry in table(config.get("marketplaces")).items():
        if isinstance(entry, dict):
            local = entry.get("source_type") == "local"
            paths = entry.get("sparse_paths")
            catalogs[name] = Catalog(name, "directory" if local else "git", str(entry.get("source") or ""),
                                     str(entry.get("ref") or ""),
                                     tuple(str(path) for path in paths) if isinstance(paths, list) else ())

    def readd(catalog: Catalog) -> List[str]:
        return ["plugin", "marketplace", "add", catalog.where,
                *(["--ref", catalog.ref] if catalog.ref and catalog.kind != "directory" else []),
                *[word for path in catalog.sparse for word in ("--sparse", path)]]

    verbs = {
        "remove": [["plugin", "remove"]],
        "forget": [["plugin", "marketplace", "remove"]],
        "add": [["plugin", "marketplace", "add", "{repo}", "--ref", "{branch}",
                 *[word for path in CODEX_SPARSE for word in ("--sparse", path)]]],
        "add_local": [["plugin", "marketplace", "add", "{folder}"]],
        "refresh": [] if context.source.local else [["plugin", "marketplace", "upgrade", "{catalog}"]],
        "install": [["plugin", "add", "{plugin}@{catalog}"]],
        "update": [["plugin", "add", "{plugin}@{catalog}"]],
        "readd": readd,
    }
    return marketplace_app(app, here, context, codex_cli(here), catalogs, plugins, verbs, CODEX_SPARSE)


def git_origin(folder: Path) -> Optional[str]:
    """The ``origin`` URL in a git working copy's config, read as bytes (a config holds any encoding a person's
    name came in)."""
    try:
        config = (Path(folder) / ".git" / "config").read_bytes().decode("utf-8", "replace")
    except OSError:
        return None
    found = re.search(r'\[remote "origin"\][^\[]*?url\s*=\s*(\S+)', config)
    return found.group(1) if found else None


def clone_problem(here: Here, path: Path) -> Optional[str]:
    """Why a git clone of ours may not be updated or removed, or None: it must have no change of its own (``git
    status --porcelain`` empty), be on the ``latest`` branch, tracking it, with no commit of its own."""
    git = here.which("git")
    if not git:
        return "git is needed to check it"
    ran = here.run([git, "-C", path, "status", "--porcelain=v1", "--branch"], timeout=60)
    if not ran.ok:
        return f"git could not read it ({ran.last()})"
    lines = ran.out.splitlines()
    head = lines[0] if lines and lines[0].startswith("## ") else ""
    branch = head[3:].split("...", 1)[0].strip()
    if branch != BRANCH:
        return f"it is on {branch or 'no branch'}, not {BRANCH}"
    if "..." not in head:
        return f"its {BRANCH} tracks no branch on GitHub"
    if "[ahead" in head or "ahead " in head.partition("[")[2]:
        return "it has commits of its own"
    if [line for line in lines[1:] if line.strip()]:
        return "it has changes not committed"
    return None


def cursor(app: App, here: Here, context: Context) -> Outcome:
    """Cursor: a clone of the ``latest`` branch in its local plugins folder (``~/.cursor/plugins/local``). Where
    Claude Code has our plugin, Cursor loads that one (as earlier releases measured), so its own copy of ours goes.
    Earlier copies: 0.10.0-0.11.11's plain copy (marked ``.text-to-cad-copy``), a development copy
    (``.text-to-cad-dev``), both deleted once ours is in. A clone is updated or removed only when it has
    nothing of its own (``clone_problem``); a link there is never followed or changed. Verified: docs
    https://cursor.com/docs/plugins (a plugin is a folder in ~/.cursor/plugins/local; a symlink there is skipped).
    That Cursor loads Claude Code's plugins is not in its docs: earlier releases' observation."""
    base = here.home / ".cursor"
    if not base.is_dir() and not here.which("cursor-agent"):
        return NOT_FOUND
    local = base / "plugins" / "local"
    source = context.source
    target = local / (f"{PLUGIN}-dev" if source.local else PLUGIN)
    removed, notes = [], []

    def kind(path: Path) -> Tuple[str, str]:
        if path.is_symlink():
            return "link", f"{here.shown(path)} is a link: left alone"
        if not path.exists():
            return "absent", ""
        if (path / COPY_MARK).is_file() or (path / DEV_MARK).is_file():
            return "copy", ""
        if our_repository(git_origin(path)):
            problem = clone_problem(here, path)
            return ("clone", "") if problem is None else ("kept", f"{here.shown(path)} left alone: {problem}")
        return "other", ""

    def clear(path: Path) -> None:
        """An earlier copy of ours out, once ours is in (or Claude Code's is)."""
        what, why = kind(path)
        if what in ("link", "kept"):
            notes.append(why)
        elif what == "clone":
            discard(path)
            removed.append(here.shown(path))
        elif what == "copy":
            discard(path)
            removed.append(here.shown(path))

    if context.claude_has_ours and not source.local:
        for path in (local / PLUGIN, local / f"{PLUGIN}-dev"):
            clear(path)
        return Outcome("skipped", "; ".join(["it loads Claude Code's plugin", *notes]), removed, has_ours=True)
    if source.local:
        what, why = kind(target)
        if what in ("link", "kept"):
            return Outcome("skipped", why)
        if what == "other":
            raise Failed(f"{here.shown(target)} holds something else: left alone (move it away, then run this again)")
        copy_tree(source.folder, target)
        (target / DEV_MARK).write_text(f"{source.folder}\n", encoding="utf-8")
        clear(local / PLUGIN)
        return Outcome("installed", "; ".join([f"a copy of {source.folder}", *notes]), removed)
    what, why = kind(target)
    git = here.which("git")
    if what == "link":
        return Outcome("skipped", f"{why} (Cursor does not load a link: put a clone there to use it)")
    if what == "kept":
        return Outcome("skipped", why, has_ours=True)
    if what == "other":
        raise Failed(f"{here.shown(target)} holds something else: left alone (move it away, then run this again)")
    if not git:
        raise Failed("git is needed to install it")
    if what == "clone":
        here.must([git, "-C", target, "fetch", "--quiet", "--depth", "1", "origin", BRANCH])
        here.must([git, "-C", target, "checkout", "--quiet", "-B", BRANCH, "FETCH_HEAD"])
        status = "updated"
    else:  # absent, or an earlier plain copy: the clone made beside it, then swapped in
        local.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix=".text-to-cad-new-", dir=str(local)))
        try:
            here.must([git, "clone", "--quiet", "--depth", "1", "--branch", BRANCH, URL, staging / PLUGIN])
            if swap(staging / PLUGIN, target):
                removed.append(f"{here.shown(target)}, the earlier plain copy")
        finally:
            shutil.rmtree(staging, ignore_errors=True)
        status = "updated" if what == "copy" else "installed"
    clear(local / f"{PLUGIN}-dev")
    return Outcome(status, "; ".join(notes), removed)


def gemini(app: App, here: Here, context: Context) -> Outcome:
    """Gemini CLI: its extension, installed from GitHub at ``latest`` (a copy), and installed again to update it:
    ``extensions update`` asks twice (to clone, since GitHub has no release ``latest``; to accept the skills) and
    takes no ``--consent``, so with no one to answer it waits for ever (measured, 0.62.0).
    0.10.0-0.11.11 linked ``<state>/plugin`` under the same name, which must go for ours to come in: GitHub is
    checked first, the old extension's folder and the enablement file are kept aside, and put back where the new
    one does not install. Read from ``~/.gemini/extensions/text-to-cad/.gemini-extension-install.json`` (``type``,
    ``source``, ``ref``). Verified: `gemini extensions --help` and its subcommands (`install <source> --ref
    --consent`, `update <name>`, `uninstall`, `link <path> --consent`); docs
    https://geminicli.com/docs/extensions/reference/."""
    cli = here.which("gemini")
    if not cli:
        return NOT_FOUND
    extensions = Path(here.environ.get("GEMINI_CLI_HOME") or here.home) / ".gemini" / "extensions"
    folder = extensions / PLUGIN
    source = context.source

    def record() -> Dict[str, Any]:
        return table(read_json(folder / ".gemini-extension-install.json"))

    def ours_now() -> bool:
        found = record()
        if source.local:
            return found.get("type") == "link" and same_path(found.get("source"), source.folder)
        return found.get("type") == "git" and our_repository(found.get("source")) and found.get("ref") == BRANCH

    def run(argv: List[Any], answer: Optional[str] = None) -> Ran:
        """A gemini command, run in an empty folder of its own that it is told to trust for that run alone: run in the
        person's folder (their home, often), ``--consent`` records that folder as trusted in trustedFolders.json."""
        neutral = tempfile.mkdtemp(prefix="text-to-cad-gemini-run-")
        try:
            return here.run([cli, *argv], cwd=Path(neutral), answer=answer,
                            environ={"GEMINI_CLI_TRUST_WORKSPACE": "true"})
        finally:
            shutil.rmtree(neutral, ignore_errors=True)

    def put_in() -> Ran:
        if source.local:
            return run(["extensions", "link", source.folder, "--consent"], answer="y\n")
        return run(["extensions", "install", URL, "--ref", BRANCH, "--consent"])

    if not (folder.exists() or folder.is_symlink()):
        ran = put_in()
        if not ran.ok and not ours_now():
            raise Failed(ran.last(), ran.reason)
        return Outcome("installed")
    found = record()
    same = ours_now()  # ours from GitHub already: installed again, below
    if same and source.local:
        return Outcome("updated", f"linked to {source.folder}")
    linked = found.get("type") == "link" and our_folder(here, found.get("source"))
    if not (same or linked or our_repository(found.get("source"))):
        raise Failed(f"another extension named {PLUGIN} is installed (from {found.get('source') or 'elsewhere'}): "
                     "left alone")
    source.reachable(here)
    aside = Path(tempfile.mkdtemp(prefix="text-to-cad-gemini-"))
    try:
        shutil.copytree(str(folder), str(aside / PLUGIN), symlinks=True)
        enablement = extensions / "extension-enablement.json"
        kept = enablement.read_bytes() if enablement.is_file() else None
        removed = run(["extensions", "uninstall", PLUGIN])
        if not removed.ok:
            raise Failed(f"`extensions uninstall` said: {removed.last()}", removed.reason)
        ran = put_in()
        if not ran.ok and not ours_now():
            if folder.exists() or folder.is_symlink():
                discard(folder)
            shutil.copytree(str(aside / PLUGIN), str(folder), symlinks=True)
            if kept is not None:
                enablement.write_bytes(kept)
            raise Failed(f"{ran.last()}; the earlier copy was put back", ran.reason)
    finally:
        shutil.rmtree(aside, ignore_errors=True)
    if same:
        return Outcome("updated")
    old = ("linked to " + str(found.get("source")) if linked else
           f"from {found.get('source')} at {found.get('ref') or 'its default branch'}")
    return Outcome("updated", removed=[f"{PLUGIN} {old}"])


def grok_plugins(here: Here) -> List[Dict[str, str]]:
    """Grok Build's installed plugins, from its registry (``~/.grok/installed-plugins/registry.json``): name, where
    from, git ref. A registry of another shape gives none."""
    repos = table(table(read_json(here.home / ".grok" / "installed-plugins" / "registry.json")).get("repos"))
    found = []
    for entry in repos.values():
        entry = table(entry)
        kind, path = entry.get("kind"), entry.get("path")
        if not isinstance(kind, dict) or not isinstance(path, str):
            continue
        named = entry.get("plugins")
        names = list(named) if isinstance(named, dict) else [
            table(read_json(Path(path) / ".grok-plugin" / "plugin.json") or read_json(Path(path) / "plugin.json")).get("name")]
        for name in names:
            found.append({"name": str(name), "source": str(kind.get("url") or kind.get("path") or ""),
                          "ref": str(kind.get("git_ref") or ""), "path": path})
    return found


def grok(app: App, here: Here, context: Context) -> Outcome:
    """Grok Build: ``grok plugin install earthtojake/text-to-cad@latest --trust``, then enabled; updated by ``grok
    plugin update``. Grok Build loads Claude Code's plugins (its docs), so where Claude Code has ours its own copy of
    ours goes. Removed, once ours is in: a plugin named ``cad`` from our repository (0.5.0-0.7.6). A copy of ours from
    another source is replaced (same name), GitHub checked first and the old one put back where the new one fails.
    Verified: `grok plugin --help` and its subcommands (`install <source>` with `@ref`, `--trust`; `enable`; `update
    [name]`; `uninstall`); docs https://docs.x.ai/build/features/skills-plugins-marketplaces (it reads Claude Code's
    marketplaces and plugins)."""
    cli = here.which("grok")
    if not cli:
        return NOT_FOUND
    source = context.source
    removed: List[str] = []
    old_cad, mine, other = False, None, None
    for plugin in grok_plugins(here):
        ours = our_repository(plugin["source"]) or our_folder(here, plugin["source"])
        if plugin["name"] == "cad" and ours:
            old_cad = True
        elif plugin["name"] == PLUGIN:
            if not ours:
                raise Failed(f"another plugin named {PLUGIN} is installed (from {plugin['source']}): left alone")
            current = (same_path(plugin["source"], source.folder) if source.local
                       else our_repository(plugin["source"]) and plugin["ref"] == BRANCH)
            mine, other = (plugin, None) if current else (None, plugin)

    def drop_cad() -> None:
        if old_cad:
            here.must([cli, "plugin", "uninstall", "cad"])
            removed.append("cad")

    if context.claude_has_ours and not source.local:
        for plugin in (mine, other):
            if plugin is not None:
                here.must([cli, "plugin", "uninstall", PLUGIN])
                removed.append(PLUGIN)
        drop_cad()
        return Outcome("skipped", "it loads Claude Code's plugin", removed, has_ours=True)
    if mine is not None:
        here.must([cli, "plugin", "update", PLUGIN])
        drop_cad()
        return Outcome("updated", removed=removed)
    install = [cli, "plugin", "install", str(source.folder) if source.local else f"{REPOSITORY}@{BRANCH}", "--trust"]
    if other is not None:
        source.reachable(here)
        here.must([cli, "plugin", "uninstall", PLUGIN])
        try:
            here.must(install)
            here.must([cli, "plugin", "enable", PLUGIN])
        except Failed as error:
            back = [cli, "plugin", "install", other["source"] + (f"@{other['ref']}" if other["ref"] else ""), "--trust"]
            put = here.run(back).ok and here.run([cli, "plugin", "enable", PLUGIN]).ok
            raise Failed(f"{error}; the earlier copy was {'put back' if put else 'not put back: run this again'}",
                         error.reason) from error
        removed.append(f"{PLUGIN} from {other['source']}" + (f"@{other['ref']}" if other["ref"] else ""))
        drop_cad()
        return Outcome("updated", removed=removed)
    here.must(install)
    here.must([cli, "plugin", "enable", PLUGIN])
    drop_cad()
    return Outcome("installed", removed=removed)


def antigravity_plugins(here: Here, cli: str) -> Optional[List[Dict[str, Any]]]:
    """``agy plugin list --json``'s plugins (name, source, path), or None where it gives none to read."""
    ran = here.run([cli, "plugin", "list", "--json"], timeout=60)
    if not ran.ok:
        return None
    starts = [index for index in (ran.out.find("["), ran.out.find("{")) if index >= 0]
    try:
        data = json.loads(ran.out[min(starts):]) if starts else None
    except ValueError:
        return None
    entries = data if isinstance(data, list) else table(data).get("plugins")
    return [entry for entry in entries if isinstance(entry, dict)] if isinstance(entries, list) else None


def antigravity(app: App, here: Here, context: Context) -> Outcome:
    """Antigravity. Docs https://antigravity.google/docs/plugins: ``agy plugin install <repo URL or path>``,
    ``uninstall <name>``, ``list --json`` (each plugin's ``source`` and ``path``; installed into
    ``~/.gemini/config/plugins/<name>``); no update command, no ref (``main``); it reads
    ``.antigravity-plugin/plugin.json``. The docs do not say whether installing again replaces a plugin, so an update
    installs again first; only where that fails, and only a copy ``list`` shows is ours, is it uninstalled and
    installed again, its folder kept aside and put back where the new one does not install. Not run."""
    cli = here.which("agy")
    if not cli:
        return NOT_FOUND
    source = context.source
    install = [cli, "plugin", "install", str(source.folder) if source.local else URL]
    listed = antigravity_plugins(here, cli)
    mine = next((entry for entry in listed or () if entry.get("name") == PLUGIN), None)
    theirs = mine is not None and not (our_repository(mine.get("source")) or our_folder(here, mine.get("source"))
                                       or our_folder(here, mine.get("path")))
    if theirs:
        raise Failed(f"another plugin named {PLUGIN} is installed (from {mine.get('source') or 'elsewhere'}): left alone")
    ran = here.run(install)
    if ran.ok:
        return Outcome("updated" if mine is not None else "installed")
    if mine is None:
        raise Failed(ran.last(), ran.reason)
    source.reachable(here)
    folder = Path(str(mine.get("path") or here.home / ".gemini" / "config" / "plugins" / PLUGIN))
    aside = Path(tempfile.mkdtemp(prefix="text-to-cad-agy-"))
    try:
        if folder.is_dir():
            shutil.copytree(str(folder), str(aside / PLUGIN), symlinks=True)
        here.must([cli, "plugin", "uninstall", PLUGIN])
        again = here.run(install)
        if not again.ok:
            if (aside / PLUGIN).is_dir() and not folder.exists():
                shutil.copytree(str(aside / PLUGIN), str(folder), symlinks=True)
            raise Failed(f"{again.last()}; the earlier copy was put back", again.reason)
    finally:
        shutil.rmtree(aside, ignore_errors=True)
    return Outcome("updated")


def copilot(app: App, here: Here, context: Context) -> Outcome:
    """GitHub Copilot CLI: ``plugin update text-to-cad``, else the catalog added (``plugin marketplace add
    earthtojake/text-to-cad#latest``) and our plugin installed from it (``plugin install text-to-cad@earthtojake``).
    Its ``marketplace add`` of a catalog it has already ends with exit status 1 (``Marketplace "earthtojake" already
    registered``), so where a run added the catalog and its install did not go in, or a person uninstalled the plugin
    and kept the catalog, every later run would fail at the add: the add is made only where its settings
    (``$COPILOT_HOME/settings.json``, default ``~/.copilot``: ``extraKnownMarketplaces``) do not name the catalog
    already. A catalog of that name from another source is left alone. Verified: `copilot plugin --help` and its
    subcommands, and the commands run (1.0.55, 1.0.67, 1.0.79, 1.0.114, on Linux; 1.0.114 on Windows); docs
    https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-plugin-reference. 1.0.43 takes no
    ``#ref`` (it clones ``text-to-cad#latest``), and 0.0.x has no ``plugin`` command."""
    cli = here.which("copilot")
    if not cli:
        return NOT_FOUND
    source = context.source
    if source.local:
        return Outcome("skipped", "no install from a local folder")
    words = source.words()
    if here.run([cli, "plugin", "update", PLUGIN]).ok:
        return Outcome("updated")
    settings = Path(here.environ.get("COPILOT_HOME") or here.home / ".copilot") / "settings.json"
    known = table(table(table(read_json(settings)).get("extraKnownMarketplaces")).get(source.catalog))
    where = table(known.get("source"))
    if not known:
        here.must([cli, "plugin", "marketplace", "add", "{repo}#{branch}".format(**words)])
    elif not our_repository(where.get("repo") or where.get("url")):
        raise Failed(f"the {source.catalog} catalog is another source's "
                     f"({where.get('repo') or where.get('url') or 'elsewhere'}): left alone")
    here.must([cli, "plugin", "install", "{plugin}@{catalog}".format(**words)])
    return Outcome("installed")


def desktop_config(here: Here) -> Path:
    if here.platform == "darwin":
        return here.home / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
    if here.windows:
        return Path(here.environ.get("APPDATA") or here.home / "AppData" / "Roaming") / "Claude" / "claude_desktop_config.json"
    return here.config_home() / "Claude" / "claude_desktop_config.json"


def runs_text_to_cad(entry: Any) -> bool:
    """Whether a server entry runs text-to-cad: its command is our transport's (``cad-mcp``) or an earlier server's
    (``cadgen``), or its arguments pin one of our packages or name one of our modules."""
    if not isinstance(entry, dict):
        return False
    command = os.path.basename(str(entry.get("command") or "")).lower()
    command = command[:-4] if command.endswith(".exe") else command
    if command in ("cad-mcp", "cadgen") or "cadgen" in command:
        return True
    words = entry.get("args") if isinstance(entry.get("args"), list) else []
    return any(isinstance(word, str) and (word.startswith(("cad-mcp==", "cad-server==", "cadgen=="))
                                          or word in ("cad-mcp", "cadgen", "cad_mcp", "cad_server.cli", "cadgen.cli"))
               for word in words)


def _member_spans(text: str, start: int) -> Tuple[List[Tuple[str, int, int, int]], int]:
    """The members of the JSON object whose ``{`` is at ``start``: ``(key, member start, value start, member end)``
    each, and where the object ends."""
    decoder = json.JSONDecoder()
    spaces = re.compile(r"\s*")
    members = []
    index = spaces.match(text, start + 1).end()
    if text[index] == "}":
        return members, index + 1
    while True:
        begin = index
        key, index = json.decoder.scanstring(text, index + 1)
        index = spaces.match(text, index).end()
        if text[index] != ":":
            raise ValueError("expected a colon")
        value = spaces.match(text, index + 1).end()
        _parsed, end = decoder.raw_decode(text, value)
        members.append((key, begin, value, end))
        index = spaces.match(text, end).end()
        if text[index] == "}":
            return members, index + 1
        if text[index] != ",":
            raise ValueError("expected a comma")
        index = spaces.match(text, index + 1).end()


def without_member(text: str, path: Sequence[str]) -> str:
    """``text``, a JSON object, with the member at ``path`` taken out and every other byte as it was."""
    spaces = re.compile(r"\s*")
    start = spaces.match(text).end()
    for depth, key in enumerate(path):
        members, _end = _member_spans(text, start)
        found = [member for member in members if member[0] == key]
        if not found:
            return text
        if depth < len(path) - 1:
            start = found[-1][2]
            if text[start] != "{":
                return text
            continue
        for _key, begin, _value, end in reversed(found):
            members, _end = _member_spans(text, start)
            place = next(i for i, member in enumerate(members) if member[1] == begin)
            if place + 1 < len(members):  # the comma after it, and the space up to the next member
                text = text[:begin] + text[members[place + 1][1]:]
            elif place > 0:  # the last: from the end of the one before it, so its comma goes
                text = text[:members[place - 1][3]] + text[end:]
            else:
                text = text[:begin] + text[end:]
    return text


def unused_kept_name(path: Path) -> Path:
    """A name beside ``path`` no file has: ``<name>.<date-time>.bak``, numbered where that is taken."""
    stamp = time.strftime("%Y%m%d-%H%M%S")
    candidate, number = path.with_name(f"{path.name}.{stamp}.bak"), 1
    while candidate.exists() or candidate.is_symlink():
        number += 1
        candidate = path.with_name(f"{path.name}.{stamp}-{number}.bak")
    return candidate


# What the run says for Claude Desktop where no `claude` command is here: its Code tab runs Claude Code, whose plugin
# manager takes the plugin.
DESKTOP_NO_CLAUDE = ("install the `claude` command to have the install command add text-to-cad, or add it in Claude "
                     "Code's plugin manager: claude plugin marketplace add earthtojake/text-to-cad#latest, then claude "
                     "plugin install text-to-cad@earthtojake")


def claude_desktop(app: App, here: Here, context: Context) -> Outcome:
    """Claude Desktop: nothing is installed in it (its Code tab runs Claude Code, which gets the plugin above).
    Releases 0.7.6-0.11.11 wrote our server into its config as ``mcpServers.cad``: that one member is taken out where
    it runs text-to-cad, every other byte of the file kept, the file as it was kept beside it under a name no file
    has (``unused_kept_name``); a config that is a link is edited where it points. A ``cad`` that is another
    server's, or a file that is not plain JSON, is left. Where no ``claude`` command was found to install the plugin
    with, it says what to do (``DESKTOP_NO_CLAUDE``); it runs nothing of Claude Desktop's own. Verified: docs https://modelcontextprotocol.io/quickstart/user (servers are keys of
    ``mcpServers`` in claude_desktop_config.json)."""
    path = desktop_config(here)
    if not path.parent.is_dir():
        return QUIET
    ours = context.claude_has_ours  # its Code tab has the plugin where Claude Code does
    hint = "" if context.claude_found else DESKTOP_NO_CLAUDE
    try:
        text = path.read_text(encoding="utf-8") if path.exists() else ""
        data = json.loads(text) if text.strip() else {}
    except (OSError, ValueError):
        return Outcome("skipped", "; ".join(filter(None, [f"{path.name} is not plain JSON: left alone", hint])),
                       has_ours=ours)
    servers = data.get("mcpServers") if isinstance(data, dict) else None
    if not isinstance(servers, dict) or not runs_text_to_cad(servers.get("cad")):
        return Outcome("note", hint, has_ours=ours) if hint else QUIET
    edited = without_member(text, ["mcpServers", "cad"])
    expected = dict(data)
    expected["mcpServers"] = {key: value for key, value in servers.items() if key != "cad"}
    if json.loads(edited) != expected:
        raise Failed(f"{path.name} could not be edited safely: remove mcpServers.cad by hand")
    real = Path(os.path.realpath(path))
    kept = unused_kept_name(real)
    shutil.copy2(real, kept)
    handle, temporary = tempfile.mkstemp(dir=str(real.parent), prefix=f".{real.name}.")
    with os.fdopen(handle, "w", encoding="utf-8", newline="") as out:
        out.write(edited)
    os.chmod(temporary, real.stat().st_mode & 0o777)
    computer.rename(temporary, real)
    words = f"the old cad server in its settings ({kept.name} keeps the file as it was)"
    return Outcome("removed", "; ".join(filter(None, [words, hint])), has_ours=ours)


def copy_skills(app: App, here: Here, context: Context) -> Outcome:
    """An agent with no plugin command: our skills copied into its own skills folder (only ours are replaced; a
    folder of that name that is someone else's stays)."""
    if not any(path.exists() for path in (app.marks(here) if app.marks else [])):
        return NOT_FOUND
    return put_skills(app.folder(here), here, context)


def put_skills(target: Path, here: Here, context: Context) -> Outcome:
    """Our skills copied into ``target``, a skills folder, each in place of ours there (``copy_tree``: staged, then
    swapped in, the old one deleted); a folder of that name that is not provably ours (``our_skill``) is kept. The skills are fetched before anything is touched."""
    source = context.source.skills(here)
    target.mkdir(parents=True, exist_ok=True)
    copied, kept, existed = [], [], False
    for skill in sorted(path for path in source.iterdir() if (path / "SKILL.md").is_file()):
        there = target / skill.name
        if (there.exists() or there.is_symlink()) and not our_skill(there):
            kept.append(skill.name)
            continue
        existed = copy_tree(skill, there) or existed
        copied.append(skill.name)
    words = f"{len(copied)} skills in {here.shown(target)}"
    if kept:
        words += f"; left {', '.join(kept)}: someone else's skill of that name"
    return Outcome("updated" if existed else "installed", words)


# The skill folders every earlier release may have left a loose copy of ours in: the shared ~/.agents/skills, each
# app's own, the per-agent folders 0.8.4-0.11.4's installer wrote through the Skills CLI, and the folders of the
# agents the Skills CLI served since. Each with the key of the app that reads it (None: a folder several apps read).
def loose_skill_folders(here: Here) -> List[Tuple[Path, Optional[str]]]:
    home, config = here.home, here.config_home()
    folders = [
        (home / ".agents" / "skills", None),
        (claude_dir(here) / "skills", "claude"),
        (Path(here.environ.get("CODEX_HOME") or home / ".codex") / "skills", "codex"),
        (home / ".cursor" / "skills", "cursor"),
        (home / ".grok" / "skills", "grok"),
        (Path(here.environ.get("GEMINI_CLI_HOME") or home) / ".gemini" / "skills", "gemini"),
        (home / ".copilot" / "skills", "copilot"),
        (config / "agents" / "skills", None),
        (home / ".gemini" / "antigravity" / "skills", "antigravity"),
        (home / ".gemini" / "antigravity-cli" / "skills", "antigravity"),
        (home / ".factory" / "skills", "droid"),
        (home / ".kilo" / "skills", "kilo"),
        (home / ".kilocode" / "skills", "kilo"),
        (config / "opencode" / "skills", "opencode"),
        (home / ".codeium" / "windsurf" / "skills", "windsurf"),
        (home / ".openclaw" / "skills", "openclaw"),
        (home / ".clawdbot" / "skills", "openclaw"),
        (home / ".moltbot" / "skills", "openclaw"),
        (config / "goose" / "skills", "goose"),
        (home / ".kiro" / "skills", "kiro"),
        (hermes_home(here) / "skills", "hermes"),
        (home / ".roo" / "skills", "roo"),
        (home / ".trae" / "skills", "trae"),
        (home / ".cline" / "skills", "cline"),
        (config / "amp" / "skills", "amp"),
    ]
    return list(dict(folders).items())


def copied_folders(here: Here, apps: Sequence[App]) -> List[Path]:
    """The skills folders the table copies our skills into: there our current skills are replaced in place
    (``put_skills``), so the loose cleanup takes only the retired ones."""
    found = [app.folder(here) for app in apps if app.folder is not None]
    return found + ([hermes_home(here) / "skills"] if any(app.key == "hermes" for app in apps) else [])


def skills_locks(here: Here) -> List[Path]:
    """The Skills CLI's records of what it installed globally: in ``$XDG_STATE_HOME/skills`` where that is set,
    else ``~/.agents`` (both read, whichever the CLI used)."""
    state = here.environ.get("XDG_STATE_HOME")
    return ([Path(state) / "skills" / ".skill-lock.json"] if state else []) + [here.home / ".agents" / ".skill-lock.json"]


def remove_loose_skills(here: Here, context: Context, outcomes: Dict[str, Outcome],
                        apps: Sequence[App] = ()) -> Outcome:
    """The loose copies of our skills (``our_skill``: one of our names AND our repository as our releases wrote
    it), after the apps, so an app loses its loose copies only once it has ours: a folder one app reads only where
    that app now has our plugin; a folder several apps read only where every app found has it; a folder the table
    copies into only its retired names (its current ones were replaced in place). A link to ours is unlinked, never
    followed; a copy deleted. The Skills CLI's record of a
    skill (``skills_locks``) goes once no copy is left in ``~/.agents/skills``, only an entry whose source is our
    repository or the plugin folder 0.10.0-0.11.11 wrote in cad's state folder. No ``npx skills remove``: it removes
    by name alone, from folders this does not read, and our names are common words."""
    found = [outcome for outcome in outcomes.values() if outcome is not NOT_FOUND and outcome is not QUIET]
    # A shared folder only after a run over every app (a development install may name a few).
    every = bool(found) and all(outcome.ours for outcome in found) and {app.key for app in (apps or APPS)} >= {app.key for app in APPS}
    copied = [os.path.normcase(os.path.realpath(path)) for path in copied_folders(here, APPS)]
    names = {app.key: app.name for app in APPS}
    chosen: List[Path] = []
    waiting = []
    for folder, owner in loose_skill_folders(here):
        if not folder.is_dir():
            continue
        copies_into = os.path.normcase(os.path.realpath(folder)) in copied
        if copies_into:
            allowed = RETIRED_SKILLS
        elif (every if owner is None else table(outcomes).get(owner, NOT_FOUND).ours):
            allowed = (*SKILLS, *RETIRED_SKILLS)
        else:
            allowed = RETIRED_SKILLS
        for name in (RETIRED_SKILLS if copies_into else (*SKILLS, *RETIRED_SKILLS)):
            path = folder / name
            if not (path.exists() or path.is_symlink()) or not our_skill(path):
                continue
            if name in allowed:
                chosen.append(path)
            else:
                waiting.append((folder, owner))
    for path in chosen:
        discard(path)  # a link unlinked, never followed
    for lock in skills_locks(here):
        record = read_json(lock)
        entries = record.get("skills") if isinstance(record, dict) else None
        if not isinstance(entries, dict):
            continue
        shared = here.home / ".agents" / "skills"
        mine = [name for name, entry in entries.items() if name in (*SKILLS, *RETIRED_SKILLS) and isinstance(entry, dict)
                and not ((shared / name).exists() or (shared / name).is_symlink())
                and any(our_repository(entry.get(key)) or (isinstance(entry.get(key), str) and os.path.isabs(entry[key])
                                                            and any(within(entry[key], state) for state in here.state_dirs()))
                        for key in ("source", "sourceUrl"))]
        if mine:
            for name in mine:
                del entries[name]
            lock.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    notes = []
    for folder, owner in dict.fromkeys(waiting):
        who = names.get(owner, owner) if owner else "every app found here"
        notes.append(f"kept the ones in {here.shown(folder)} until {who} has the plugin")
    if not chosen:
        return Outcome("skipped", "; ".join(notes)) if notes else QUIET
    places = sorted({here.shown(path.parent) for path in chosen})
    words = f"{len(chosen)} old copies of our skills, in {', '.join(places)}"
    return Outcome("removed", "; ".join([words, *notes]))


def hermes_home(here: Here) -> Path:
    return Path(here.environ.get("HERMES_HOME") or here.home / ".hermes")


def hermes(app: App, here: Here, context: Context) -> Outcome:
    """Hermes Agent: our skills copied into its own skills folder, ``$HERMES_HOME/skills`` (default
    ``~/.hermes/skills``), where Hermes reads a user's skills, each a folder with its SKILL.md; copied again to
    update. Found by the ``hermes`` command or its home folder. Then, once the skills are in, the plugin of ours
    0.11.x's installer installed with ``hermes plugins install`` (``plugins/text-to-cad``, ours by Hermes's install
    record or our repository in its manifests) is removed with ``hermes plugins remove``, where the command is here.
    No plugin: Hermes takes a plugin only by the Agent Plugins standard's root ``plugin.json``, which Codex would read
    in place of its own manifest. Verified: docs https://hermes-agent.nousresearch.com/docs/user-guide/features/skills
    (``~/.hermes/skills`` is the skills folder); its source (``tools/skills_tool.py``: ``HERMES_HOME/skills``, every
    SKILL.md beneath it); ``hermes skills list`` listing the copied skills with HERMES_HOME in a scratch folder."""
    cli = here.which("hermes")
    home = hermes_home(here)
    if not cli and not home.is_dir():
        return NOT_FOUND
    plugin = home / "plugins" / PLUGIN
    entry = table(table(read_json(home / "plugins" / ".install-metadata.json")).get(PLUGIN))
    old = plugin.is_dir() and (our_repository(entry.get("source")) or our_folder(here, plugin))
    outcome = put_skills(home / "skills", here, context)
    if old:
        removal = here.run([cli, "plugins", "remove", PLUGIN]) if cli else None
        if removal is not None and removal.ok:
            outcome.removed = [f"the {PLUGIN} plugin"]
        elif removal is not None:
            outcome.words += f"; the old {PLUGIN} plugin stays (hermes said: {removal.last()})"
        else:
            outcome.words += (f"; the old {PLUGIN} plugin in {here.shown(plugin)} stays until the hermes command "
                              f"removes it: hermes plugins remove {PLUGIN}")
    return outcome


def _pi_installed(here: Here) -> bool:
    try:
        return f"github.com/{REPOSITORY}" in (here.home / ".pi" / "agent" / "settings.json").read_text(
            encoding="utf-8", errors="replace")
    except OSError:
        return False


def _qwen_installed(here: Here) -> bool:
    return (here.home / ".qwen" / "extensions" / PLUGIN).is_dir()


def _folder_agent(key: str, name: str, folder: Callable[[Here], Path], *marks: Callable[[Here], Path]) -> App:
    return App(key, name, folder=folder, marks=lambda here: [mark(here) for mark in marks])


# THE TABLE. Order matters only where it says: Claude Code first (Cursor and Grok Build load its plugin; Claude
# Desktop says what to do where no `claude` command was found).
APPS: Tuple[App, ...] = (
    App("claude", "Claude Code", command="claude", handler=claude_code),
    App("claude-desktop", "Claude Desktop", handler=claude_desktop),
    App("codex", "Codex", command="codex", handler=codex),
    App("cursor", "Cursor", handler=cursor),
    App("gemini", "Gemini CLI", command="gemini", handler=gemini),
    App("grok", "Grok Build", command="grok", handler=grok),
    # Qwen Code. Docs https://qwenlm.github.io/qwen-code-docs/en/users/extension/introduction/ (install, update) and its
    # source, packages/cli/src/commands/extensions/install.ts (--ref, --consent). Not run. Where it keeps an extension
    # (~/.qwen/extensions/<name>) is Gemini CLI's layout, unverified.
    App("qwen", "Qwen Code", command="qwen",
        install=[["extensions", "install", "{url}", "--ref", "{branch}", "--consent"]],
        update=[["extensions", "update", "{plugin}"]],
        local=[["extensions", "install", "{folder}", "--consent"]], installed=_qwen_installed),
    # Hermes Agent (``hermes``, above): the skills in its own folder, and the plugin of ours 0.11.x installed removed.
    App("hermes", "Hermes Agent", command="hermes", handler=hermes),
    # Factory Droid. Docs https://docs.factory.com/cli/configuration/plugins: it reads .claude-plugin/marketplace.json;
    # the catalog's name comes from the source (`owner/repo` -> the repo's name; a `#ref` is appended to it), so this
    # adds no ref (main) to keep the name text-to-cad, as superpowers does. Not run.
    App("droid", "Factory Droid", command="droid",
        install=[["plugin", "marketplace", "add", "{repo}"], ["plugin", "install", "{plugin}@text-to-cad", "--scope", "user"]],
        update=[["plugin", "marketplace", "update", "text-to-cad"], ["plugin", "update", "{plugin}@text-to-cad", "--scope", "user"]]),
    # Devin CLI. Docs https://docs.devin.ai/cli/extensibility/plugins/overview (install owner/repo -y; no ref: main;
    # update <name>; it reads .claude-plugin/plugin.json; managing plugins needs a person signed in). Run, signed out
    # (3000.14 on Windows): each command ends with exit status 1 and "Error: You must be logged in to manage plugins.
    # Run `devin auth login` first.", so it is skipped there; not run signed in.
    App("devin", "Devin CLI", command="devin",
        install=[["plugins", "install", "{repo}", "-y"]], update=[["plugins", "update", "{plugin}"]],
        local=[["plugins", "install", "--local", "{folder}", "-y"]], signed_out=r"must be logged in"),
    # Antigravity (``antigravity``, above): installed again to update; uninstalled only where that fails. Not run.
    App("antigravity", "Antigravity", command="agy", handler=antigravity),
    # GitHub Copilot CLI (``copilot``, above): updated, else the catalog added where it has none, and installed.
    App("copilot", "GitHub Copilot CLI", command="copilot", handler=copilot),
    # Pi. Docs https://docs.pi.dev/latest/packages (`pi install git:github.com/o/r@ref`; personal installs are recorded
    # in ~/.pi/agent/settings.json; `pi update` never moves a configured ref, so an update is the install again).
    # Lane C ran the install from a local copy; not run against GitHub here.
    App("pi", "Pi", command="pi",
        install=[["install", "git:github.com/{repo}@{branch}"]], update=[["install", "git:github.com/{repo}@{branch}"]],
        local=[["install", "{folder}"]], installed=_pi_installed),
    # Muse (Meta's Muse Code). From superpowers' practice and Muse's changelog; not run. It installs a plugin from a local
    # folder and copies it into its own cache (so the fetched `latest` is temporary), then `approve` lets it load;
    # `update <name>`, else the install again. It reads .muse-plugin/plugin.json.
    App("muse", "Muse", command="muse",
        install=[["plugins", "install", "{fetched}"], ["plugins", "approve", "{plugin}"]],
        update=[["plugins", "update", "{plugin}"]],
        local=[["plugins", "install", "{folder}"], ["plugins", "approve", "{plugin}"]]),
    # Agents with no plugin command: the skills copied into each one's own folder, where each one's docs (or, for
    # Windsurf and Goose, the Skills CLI's agent table and our earlier installers) say it reads them. Kilo: docs
    # https://kilo.ai/docs/features/skills (global skills in ~/.kilo/skills; ~/.kilocode is the older extension's
    # folder, which finds it too). Not run.
    _folder_agent("cline", "Cline", lambda h: h.home / ".cline" / "skills", lambda h: h.home / ".cline"),
    _folder_agent("amp", "Amp", lambda h: h.config_home() / "amp" / "skills", lambda h: h.config_home() / "amp"),
    _folder_agent("openclaw", "OpenClaw", lambda h: h.home / ".openclaw" / "skills", lambda h: h.home / ".openclaw"),
    _folder_agent("kilo", "Kilo Code", lambda h: h.home / ".kilo" / "skills", lambda h: h.home / ".kilo",
                  lambda h: h.home / ".kilocode"),
    _folder_agent("kiro", "Kiro CLI", lambda h: h.home / ".kiro" / "skills", lambda h: h.home / ".kiro"),
    _folder_agent("roo", "Roo Code", lambda h: h.home / ".roo" / "skills", lambda h: h.home / ".roo"),
    _folder_agent("trae", "Trae", lambda h: h.home / ".trae" / "skills", lambda h: h.home / ".trae"),
    _folder_agent("windsurf", "Windsurf", lambda h: h.home / ".codeium" / "windsurf" / "skills",
                  lambda h: h.home / ".codeium" / "windsurf"),
    _folder_agent("goose", "Goose", lambda h: h.config_home() / "goose" / "skills", lambda h: h.config_home() / "goose"),
    _folder_agent("opencode", "OpenCode", lambda h: h.config_home() / "opencode" / "skills",
                  lambda h: h.config_home() / "opencode"),
)


# --- every app, in turn ------------------------------------------------------------------------------


@dataclass
class Report:
    """What the app phase did: its lines, in the order printed, each app's outcome by key and how many seconds it
    took, and whether the run's deadline stopped it before every app was done (``stopped``: the apps after it have no
    outcome)."""

    lines: List[str]
    outcomes: Dict[str, Outcome]
    seconds: Dict[str, float] = field(default_factory=dict)
    stopped: bool = False

    def __contains__(self, line: str) -> bool:
        return line in self.lines

    def statuses(self) -> Dict[str, str]:
        """Each app's status by its key, as a report of the run gives it: ``installed``, ``updated``, ``removed``,
        ``skipped`` (a note, or nothing to say, too), ``failed``, or ``not found``."""
        return {key: "not found" if outcome is NOT_FOUND else "skipped" if outcome.status == "note" else outcome.status
                for key, outcome in self.outcomes.items()}

    @property
    def found(self) -> List[Outcome]:
        return [outcome for outcome in self.outcomes.values() if outcome is not NOT_FOUND and outcome is not QUIET]

    @property
    def changed(self) -> bool:
        return any(outcome.status in ("installed", "updated") for outcome in self.found)

    @property
    def all_failed(self) -> bool:
        return bool(self.found) and all(outcome.status == "failed" for outcome in self.found)


def install_apps(here: Here, source: Source, apps: Sequence[App] = APPS,
                 say: Callable[[str], None] = lambda line: print(line, flush=True),
                 live: Optional[Live] = None,
                 each: Optional[Callable[[str, Outcome, float], None]] = None) -> Report:
    """``apps``, each in turn: ours in, then old copies out, each app's line said as it finishes; one line for the
    loose skills, one counting the apps not found. ``live``: a person's terminal, told which app is being set up, and
    each line said with its mark. ``each``: told every app's key, outcome and seconds as it is done, for whoever must
    know how far the run got should it never return. Where the run's deadline passes (``Here.expired``), no further
    app is begun and nothing more is removed."""
    context = Context(source)
    lines: List[str] = []
    outcomes: Dict[str, Outcome] = {}
    seconds: Dict[str, float] = {}
    missing = []

    def tell(line: str, status: str = "") -> None:
        lines.append(line)
        try:
            say(live.mark(line, status) if live is not None else line)
        except (OSError, ValueError):  # a line the output cannot take is lost, never the apps after it
            pass

    for app in apps:
        if here.expired:
            if live is not None:
                live.end()
            return Report(lines, outcomes, seconds, stopped=True)
        if live is not None:
            live.begin(app.name)
        began = time.monotonic()
        try:
            outcome = app.run(here, context)
        except Failed as error:
            outcome = Outcome("failed", str(error), reason=error.reason)
        except Exception as error:  # noqa: BLE001 - one app's surprise is that app's failure, never the run's
            outcome = Outcome("failed", f"{type(error).__name__}: {error}", reason=EXCEPTION)
        outcomes[app.key] = outcome
        seconds[app.key] = time.monotonic() - began
        if each is not None:
            each(app.key, outcome, seconds[app.key])
        if outcome is NOT_FOUND:
            missing.append(app.name)
        elif outcome is not QUIET:
            tell(outcome.line(app.name), outcome.status)
    if live is not None:
        live.begin("Loose skills")
    try:
        loose = remove_loose_skills(here, context, outcomes, apps)
    except Exception as error:  # noqa: BLE001
        loose = Outcome("failed", f"{type(error).__name__}: {error}")
    if live is not None:
        live.end()
    if loose is not QUIET:
        tell(loose.line("Loose skills"), loose.status)
    if missing:
        tell(f"{len(missing)} other supported apps were not found here.")
    return Report(lines, outcomes, seconds, stopped=here.expired)
