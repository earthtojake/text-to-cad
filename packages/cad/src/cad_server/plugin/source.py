"""Where the plugin comes from, and what is ours: the GitHub repository and its ``latest`` branch, the names we ever
used (our catalogs, our plugins, our skills, current and retired), how a catalog, a folder or a skill of ours says it
is ours (``our_repository``, ``our_folder``, ``our_skill``), and the source one run installs from (``Source``: the
``latest`` branch, fetched once where an app needs its files; or, for a checkout's development install, a local
folder).

What is removed is only what is provably ours: our names AND a sign that it is ours (our catalog, a path in cad's
state folder, a git origin naming our repository, a SKILL.md whose front matter or provenance line names our
repository). A store's copy and every plugin or skill of someone else's are never touched.

The standard library alone.
"""

from __future__ import annotations

import re
import shutil
import tarfile
import tempfile
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from .computer import NETWORK, Failed, Here, within

REPOSITORY = "earthtojake/text-to-cad"
URL = f"https://github.com/{REPOSITORY}"
BRANCH = "latest"
PLUGIN = "text-to-cad"
CATALOG = "earthtojake"          # the repository's catalog: a GitHub copy is text-to-cad@earthtojake
DEV_CATALOG = "earthtojake-dev"  # a checkout's development install
LOCAL_CATALOG = "text-to-cad"    # the folder catalog 0.10.0-0.11.11's installer wrote, <state>/plugin
# Every catalog of ours an app may hold. Of these, the one the source installs from is kept and brought up to date;
# the others are removed with their plugins, once ours is in.
OUR_CATALOGS = (LOCAL_CATALOG, CATALOG, DEV_CATALOG)
# The plugin names we ever used: `cad` until 0.7.6, `text-to-cad` since.
OUR_PLUGINS = ("text-to-cad", "cad")
SKILLS = ("cad", "engineering-drawing", "fea", "pcb", "print3d", "render", "robot-simulation", "sendcutsend")
# Skills an earlier release shipped and this one does not (implicit-cad: releases before 0.5).
RETIRED_SKILLS = ("bambu-labs", "dfam-check", "dfm", "dxf", "gcode", "pcb-dfm", "sdf", "simulation", "srdf",
                  "step-parts", "urdf", "cad-viewer", "cad-mcp-setup", "implicit-cad")
# How a SKILL.md of ours says so, checked in every release tagged from v0.5.0 to v0.11.10 (every skill of each):
# 0.10.0 and later, its front matter's `metadata:` block holds `repository: earthtojake/text-to-cad`; 0.5.0 to
# 0.8.4, its body has this line, word for word. A skill that merely mentions the repository is not ours.
PROVENANCE_LINE = "Provenance: maintained in [earthtojake/text-to-cad](https://github.com/earthtojake/text-to-cad)."
# Marks earlier installers wrote: in Cursor's plain copy (0.10.0-0.11.11), in a development install's copy.
COPY_MARK = ".text-to-cad-copy"
DEV_MARK = ".text-to-cad-dev"


def our_repository(source: Any) -> bool:
    """Whether a git source names this repository: owner/repo, its URL, with or without .git."""
    if not isinstance(source, str):
        return False
    text = source.strip().rstrip("/")
    text = text[:-4] if text.endswith(".git") else text
    text = re.sub(r"^(https?://|git@)", "", text).replace("github.com:", "github.com/")
    return text in (REPOSITORY, f"github.com/{REPOSITORY}")


def our_folder(here: Here, path: Any) -> bool:
    """Whether a local plugin folder is ours: one an earlier installer wrote into cad's state folder
    (``<state>/plugin``), or one whose manifest names our repository (a checkout, a development install)."""
    if not path or not isinstance(path, (str, Path)):
        return False
    if any(within(path, state) for state in here.state_dirs()):
        return True
    parts = Path(str(path)).parts
    if len(parts) >= 2 and parts[-1] == "plugin" and parts[-2] in ("cad", "cad-state"):
        return True
    for manifest in (".claude-plugin/marketplace.json", ".claude-plugin/plugin.json", "gemini-extension.json"):
        try:
            if URL in (Path(path) / manifest).read_text(encoding="utf-8", errors="replace"):
                return True
        except OSError:
            continue
    return False


def front_matter(text: str) -> Optional[List[str]]:
    """The lines of a SKILL.md's front matter, between its first two ``---`` lines."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    for index, line in enumerate(lines[1:], 1):
        if line.strip() == "---":
            return lines[1:index]
    return None


def skill_name(text: str) -> Optional[str]:
    """The ``name`` in a SKILL.md's front matter."""
    for line in front_matter(text) or ():
        if line.startswith("name:"):
            return line[len("name:"):].strip().strip("\"'")
    return None


def _metadata_repository(header: Sequence[str]) -> Optional[str]:
    """``metadata.repository`` in front matter lines: the indented ``repository:`` under a ``metadata:`` line."""
    inside = False
    for line in header:
        if not line.strip():
            continue
        if not line[:1].isspace():
            inside = line.split("#", 1)[0].strip() == "metadata:"
            continue
        if inside and line.strip().startswith("repository:"):
            return line.strip()[len("repository:"):].split(" #", 1)[0].strip().strip("\"'")
    return None


def our_skill(folder: Path) -> Optional[bool]:
    """Whether a skill folder is ours: its SKILL.md has one of our skills' names (current or retired) and says it
    is ours as our releases wrote it (``PROVENANCE_LINE``): its front matter's ``metadata.repository`` is our
    repository, or its body has our provenance line. None where it holds no readable SKILL.md (a link to nowhere, an
    empty folder): not ours to judge."""
    try:
        text = (Path(folder) / "SKILL.md").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    header = front_matter(text)
    if header is None or skill_name(text) not in (*SKILLS, *RETIRED_SKILLS):
        return False
    return (_metadata_repository(header) == REPOSITORY
            or any(line.strip() == PROVENANCE_LINE for line in text.splitlines()))


# --- where the plugin comes from ---------------------------------------------------------------------


@dataclass
class Source:
    """Where the plugin comes from: the GitHub repository's ``latest`` branch, or, for a development install, a local
    folder holding the plugin (``folder``) whose catalog is ``catalog``."""

    folder: Optional[Path] = None
    catalog: str = CATALOG
    skills_dir: Optional[Path] = None
    _scratch: Optional[str] = None
    _failed: Optional[Failed] = None
    _reachable: Optional[str] = None

    @property
    def local(self) -> bool:
        return self.folder is not None

    def words(self) -> Dict[str, str]:
        return {"repo": REPOSITORY, "url": URL, "branch": BRANCH, "plugin": PLUGIN, "catalog": self.catalog,
                "folder": str(self.folder or "")}

    def reachable(self, here: Here) -> None:
        """Before anything of ours is taken out to be replaced: that the ``latest`` branch can be reached
        (``git ls-remote``, else the branch's archive answering). ``Failed`` where it cannot, nothing changed."""
        if self.local:
            return
        if self._reachable is None:
            git = here.which("git")
            if git:
                ran = here.run([git, "ls-remote", "--exit-code", "--heads", URL, BRANCH], timeout=60)
                self._reachable = "" if ran.ok else ran.last()
            else:
                try:
                    request = urllib.request.Request(f"https://codeload.github.com/{REPOSITORY}/tar.gz/refs/heads/{BRANCH}",
                                                     method="HEAD")
                    with urllib.request.urlopen(request, timeout=20):
                        self._reachable = ""
                except Exception as error:  # noqa: BLE001 - any failure means not reachable
                    self._reachable = type(error).__name__
        if self._reachable:
            raise Failed(f"GitHub could not be reached ({self._reachable}): the copy there was left as it was",
                         NETWORK)

    def skills(self, here: Here) -> Path:
        """The skills folder to copy from: the local one, else the ``latest`` branch's, fetched once (git, else
        the branch's tarball)."""
        if self.skills_dir is not None:
            return self.skills_dir
        if self._failed is not None:
            raise Failed(str(self._failed), self._failed.reason)
        try:
            return self._fetch(here)
        except Failed as error:
            self._failed = error
            raise

    def _fetch(self, here: Here) -> Path:
        self._scratch = tempfile.mkdtemp(prefix="text-to-cad-")
        target = Path(self._scratch) / "repo"
        git = here.which("git")
        if git and here.run([git, "clone", "--quiet", "--depth", "1", "--branch", BRANCH, URL, target]).ok:
            self.skills_dir = target / "skills"
            return self.skills_dir
        shutil.rmtree(target, ignore_errors=True)
        archive = Path(self._scratch) / "latest.tar.gz"
        try:
            with urllib.request.urlopen(f"https://codeload.github.com/{REPOSITORY}/tar.gz/refs/heads/{BRANCH}",
                                        timeout=60) as answer, open(archive, "wb") as out:
                shutil.copyfileobj(answer, out)
            with tarfile.open(archive) as tar:
                members = [member for member in tar.getmembers() if member.isfile() or member.isdir()]
                if any(member.name.startswith("/") or ".." in Path(member.name).parts for member in members):
                    raise Failed("the downloaded archive is not a plain folder")
                tar.extractall(target, members=members, **({"filter": "data"} if hasattr(tarfile, "data_filter") else {}))
        except (OSError, tarfile.TarError, ValueError) as error:
            raise Failed(f"could not download the skills ({type(error).__name__}): nothing was changed",
                         NETWORK) from error
        roots = [path for path in target.iterdir() if (path / "skills").is_dir()]
        if not roots:
            raise Failed("the downloaded archive has no skills folder")
        self.skills_dir = roots[0] / "skills"
        return self.skills_dir

    def root(self, here: Here) -> Path:
        """The plugin's folder: the local one, else the ``latest`` branch fetched once (``skills``)."""
        return self.folder if self.folder is not None else self.skills(here).parent

    def close(self) -> None:
        if self._scratch:
            shutil.rmtree(self._scratch, ignore_errors=True)
