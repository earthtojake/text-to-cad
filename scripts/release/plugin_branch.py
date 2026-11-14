#!/usr/bin/env python3
"""Build the plugin alone, as the branches installers follow take it, check it, and commit it.

Installers clone a branch and take its tree as the plugin. On `main` that tree is the
monorepo: thousands of files, a workspace npm installs, workflows and binaries that claude.ai's
directory holds for a reviewer -- and a release's pins from the merge on, before PyPI has the
wheel. So installers follow branches that only Publish Release writes, once the wheel is on
PyPI: one commit per release whose tree is only the plugin -- the manifests and the icon, the
MCP configs they name, `skills/`, `LICENSE`, and the README, with each link to a file outside
that tree pointed at the release commit on GitHub (CONTRIBUTING.md, "The install branches").
Two copies, differing in what they carry:

- `latest`: the newest release, which every documented install command names. Every host's
  manifest and MCP config, the marketplace catalog, which lists the plugin at the root of the
  branch it is read from, Codex's manifest and config, Grok Build's manifest, and the Agent
  Plugins standard's. Claude's manifest there is main's: it names no server, so Claude Code gets
  the skills alone.
- `directory` (pushed to `claude-plugin`): claude.ai's plugin directory. Claude's manifest and
  icon, `skills/`, `LICENSE` and the README: the skills alone, no MCP server and no hooks, and
  only the file types the directory accepts from an organization it has not verified
  (`type_errors`): another file type anywhere in it fails the build. It holds every skill.

Each copy runs the release it was built from, on a delivery channel: `latest` is our own text, every
pin as main has it (`cad +<VERSION> <verb>`), the default channel; the directory's copy has every pin
stamped `@claude` (`cad +<VERSION>@claude <verb>`, `channel_stamp.py`), the channel claude.ai's directory
delivers, so its updates move that channel alone. No MCP config names a channel or says who updates it:
the launcher of a store that delivers one is given it as an argument (`cad-mcp --channel NAME`), and
the directory's copy carries no server at all.

The directory's copy differs from main's text in three more places, each a strict substitution that fails
the build when what it replaces is not there exactly once (`by_uvx`, `unlisted`). claude.ai's directory
flags a download piped to a shell (`curl ... | sh`) as an install-time risk, so the copy installs by the
`uvx` command the software itself runs for a version it lacks (`UVX_INSTALL`), the same on every system:
in each skill's setup block that command replaces the install script's line and the Windows sentence goes,
and in the README it replaces the Quickstart's two one-liners and the paragraph after them. Its manifest
leaves out the listing links the directory's validation does not know (`UNLISTED`); the README, which the
directory shows as the listing's description, links the same pages. No pipe-to-shell download is left
anywhere in the copy (`PIPE_TO_SHELL`).

The checks are claude.ai's file rules, the strictest of the directories
(https://claude.com/docs/plugins/pre-submission-checklist.md): a tree that breaks
one is held for a reviewer, or never validates. Publish Release runs `--check`
before anything irreversible and, on main, commits each copy and pushes it. Never
commit to those branches by hand.

    scripts/release/plugin_branch.py --check
    scripts/release/plugin_branch.py --commit --copy latest|directory [--parent REF]   # prints the commit
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from typing import NamedTuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
import channel_stamp  # noqa: E402 - beside this script: the one stamping routine, plugin_zip.py's too

REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ".claude-plugin/plugin.json"
ICON = ".claude-plugin/icon.png"
CATALOG = ".claude-plugin/marketplace.json"
FILES = (MANIFEST, ICON, ".cursor-plugin/plugin.json", "gemini-extension.json", "claude.mcp.json",
         "cursor.mcp.json", "LICENSE")
# claude.ai's directory: Claude's manifest and icon beside the skills, and nothing another host reads.
DIRECTORY_FILES = (MANIFEST, ICON, "LICENSE")
# What Claude Code's and Codex's marketplaces read besides: the catalog, and Codex's manifest and config.
MARKETPLACE_FILES = (CATALOG, ".codex-plugin/plugin.json", ".codex-plugin/logo.png", "codex.mcp.json")
# The Agent Plugins standard's manifest and server config (agent-plugins.org), which VS Code reads before
# Claude's manifest.
STANDARD_FILES = ("plugin.json", "mcp.json")
# Grok Build's manifest, which it reads before Claude's: Claude's names no server, Grok's names claude.mcp.json.
GROK_FILES = (".grok-plugin/plugin.json",)


class Copy(NamedTuple):
    files: tuple[str, ...]
    # The delivery channel every pin of the copy is stamped with (`channel_stamp.py`); None: the default, as on main.
    channel: str | None
    # Whether the copy holds only what claude.ai's directory accepts from an organization it has not
    # verified: the skills alone, in the file types `type_errors` allows.
    skills_only: bool = False
    # Whether the copy installs by `UVX_INSTALL` in place of the install script (`by_uvx`).
    uvx: bool = False
    # Keys of Claude's manifest the copy leaves out (`unlisted`).
    unlisted: tuple[str, ...] = ()


# The listing links claude.ai's directory's validation does not know (`UNKNOWN_KEY`); main's and `latest`'s
# manifests keep them.
UNLISTED = ("documentationUrl", "privacyPolicyUrl", "supportUrl", "termsOfServiceUrl")
COPIES = {
    "latest": Copy(FILES + MARKETPLACE_FILES + STANDARD_FILES + GROK_FILES, None),
    "directory": Copy(DIRECTORY_FILES, "claude", skills_only=True, uvx=True, unlisted=UNLISTED),
}
DIRECTORIES = ("skills/",)
README = "README.md"
LFS_POINTER = b"version https://git-lfs.github.com/spec/v1"
MAX_FILES = 512
MAX_TEXT_BYTES = 256 * 1024  # larger non-image files are held for a reviewer
MAX_FILE_BYTES = 5 * 1024 * 1024  # a larger file stops validation outright
# PNG, JPEG, GIF and font signatures; WebP is checked on its own. Any other binary is held.
IMAGE_OR_FONT = (b"\x89PNG\r\n\x1a\n", b"\xff\xd8\xff", b"GIF87a", b"GIF89a",
                 b"\x00\x01\x00\x00", b"OTTO", b"wOFF", b"wOF2")
IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg")
# A relative link in Markdown or HTML -- ](target) or src="target" / href="target" -- that
# is not a URL, an anchor or a root path.
LINK = re.compile(r'(?P<open>\]\(|(?:src|href)=")'
                  r'(?P<target>(?![a-zA-Z][a-zA-Z0-9+.-]*:|#|/)[^)"\s#]+)(?P<fragment>#[^)"\s]*)?')
# What claude.ai's directory accepts from an organization it has not verified: Markdown, text, JSON and
# YAML, saved as UTF-8 with no NUL byte and not starting with #!, and these images, each by its content
# whatever its name. A `LICENSE` is text with no extension.
TEXT_SUFFIXES = (".md", ".markdown", ".txt", ".json", ".yaml", ".yml")
TEXT_NAMES = ("LICENSE",)
IMAGES = {".png": (b"\x89PNG\r\n\x1a\n",), ".jpg": (b"\xff\xd8\xff",), ".jpeg": (b"\xff\xd8\xff",),
          ".gif": (b"GIF87a", b"GIF89a"), ".ico": (b"\x00\x00\x01\x00",), ".webp": ()}
# Files it refuses by name: configs Claude Code reads beside the manifest, and package managers'.
HOST_CONFIGS = {"hooks.json", ".mcp.json", ".lsp.json", "monitors.json"}
PACKAGE_CONFIGS = {"package.json", "package-lock.json", "npm-shrinkwrap.json", "pnpm-workspace.yaml", "pnpm-lock.yaml",
                   "yarn.lock", ".yarnrc.yml", ".npmrc", "bun.lock", "deno.json", "deno.jsonc", "composer.json",
                   "requirements.txt", "constraints.txt", "uv.lock", "pyproject.toml", "Pipfile"}
# What the directory's copy of Claude's manifest must not name: it carries the skills alone.
NOT_SKILLS = ("mcpServers", "hooks", "lspServers")
# The install script, as main's skills and README run it (`cad_server.updates.INSTALL` and `INSTALL_WINDOWS`'s
# script), and the `uvx` command a copy installs by in its place: the server's own line for a version
# (`cad_server._internal.launch.launch_command`) running `cad setup --add`. test_plugin_branch.py holds the three
# to the server's.
INSTALL_SCRIPT = "curl -fsSL https://texttocad.dev/install.sh | sh"
INSTALL_SCRIPT_WINDOWS = "https://www.texttocad.dev/install.ps1"
UVX_INSTALL = "uvx --no-config --managed-python --python 3.14 --from cad-server=={version} cad setup --add"
# A skill's setup block: the install script's line, and the sentence that runs it on Windows.
SKILL_DOC = re.compile(r"skills/[^/]+/SKILL\.md")
SETUP_LINE = INSTALL_SCRIPT + " -s -- --add {version}\n"
SETUP_WINDOWS = ("On Windows, in PowerShell: `& ([scriptblock]::Create((irm " + INSTALL_SCRIPT_WINDOWS
                 + "))) --add {version}`.\n")
# The README's install section: the Quickstart's two one-liners and the paragraph after them.
README_INSTALL = re.compile(
    r"^macOS and Linux:\n\n```bash\n" + re.escape(INSTALL_SCRIPT) + r"\n```\n\n"
    r"Windows, in PowerShell:\n\n```powershell\n" + re.escape(f"irm {INSTALL_SCRIPT_WINDOWS} | iex") + r"\n```\n\n"
    r"(?:[^\n]+\n)+", re.M)
README_UVX = """```bash
{command}
```

The skills run text-to-cad's `cad` command. The first time, your agent installs it with
[uv](https://docs.astral.sh/uv/), with your permission, or you run the command above yourself. It installs
text-to-cad {version} and the `cad` command and changes nothing else.
"""
# A download piped to a shell or run as a script block: what claude.ai's directory flags (`RUNTIME_FETCH_EXEC`).
_FETCH = r"(?:irm|iwr|invoke-restmethod|invoke-webrequest)"
PIPE_TO_SHELL = re.compile(
    r"\b(?:curl|wget)\b[^\n]*\|[ \t]*(?:sudo[ \t]+)?(?:ba|da|k|z)?sh\b"
    r"|\b(?:ba|z)?sh[ \t]+(?:-c[ \t]+[\"']?\$\(|<\()[ \t]*(?:curl|wget)\b"
    rf"|\b{_FETCH}\b[^\n]*\|[ \t]*(?:iex|invoke-expression)\b"
    rf"|\[scriptblock\]::create\(\(?[ \t]*{_FETCH}\b", re.I)


def git(root: Path, *args: str, stdin: bytes | None = None, env: dict | None = None) -> bytes:
    return subprocess.run(["git", "-C", str(root), *args], input=stdin, env=env,
                          check=True, capture_output=True).stdout


def tracked(root: Path) -> dict[str, tuple[str, str]]:
    """Every tracked path, with its git mode and blob id."""
    entries = {}
    for record in filter(None, git(root, "ls-files", "-z", "-s").split(b"\0")):
        meta, path = record.decode("utf-8").split("\t", 1)
        mode, blob, _stage = meta.split()
        entries[path] = (mode, blob)
    return entries


def read_blobs(root: Path, blobs: list[str]) -> dict[str, bytes]:
    out = git(root, "cat-file", "--batch", stdin="".join(f"{blob}\n" for blob in blobs).encode())
    contents, at = {}, 0
    for blob in blobs:
        header_end = out.index(b"\n", at)
        size = int(out[at:header_end].split()[2])
        contents[blob] = out[header_end + 1:header_end + 1 + size]
        at = header_end + 1 + size + 1
    return contents


def holds(paths: set[str], target: str) -> bool:
    target = target.removeprefix("./").rstrip("/")
    return target in paths or any(path.startswith(f"{target}/") for path in paths)


def readme_for_tree(text: str, tree: set[str], repository: set[str], url: str, commit_id: str,
                    errors: list[str]) -> str:
    """The README with each relative link to a file outside the tree pointed at that file on GitHub."""
    def point(match: re.Match) -> str:
        target = match["target"]
        if holds(tree, target):
            return match[0]
        if not holds(repository, target):
            errors.append(f"{README} links to {target}, which is not in the repository")
            return match[0]
        kind = "raw" if target.lower().endswith(IMAGE_SUFFIXES) else "blob"
        path = target.removeprefix("./")
        return f'{match["open"]}{url}/{kind}/{commit_id}/{path}{match["fragment"] or ""}'
    return LINK.sub(point, text)


def stamped(tree: dict[str, tuple[str, bytes]], version: object,
            channel: str) -> tuple[dict[str, tuple[str, bytes]], list[str]]:
    """The tree with every pin of the release (the manifest's `version`) stamped `@channel` (`channel_stamp.stamp`),
    and what fails the build."""
    if not isinstance(version, str) or not version:
        return tree, [f"{MANIFEST}: no `version`, so its pins cannot be stamped @{channel}"]
    files, errors = channel_stamp.stamp({path: data for path, (_mode, data) in tree.items()}, version, channel)
    return {path: (mode, files[path]) for path, (mode, _data) in tree.items()}, errors


def by_uvx(tree: dict[str, tuple[str, bytes]], version: str) -> tuple[dict[str, tuple[str, bytes]], list[str]]:
    """The tree installing by `UVX_INSTALL` for `version` in place of the install script, and what fails the build.

    In each skill's setup block the script's line becomes the command and the Windows sentence goes; a skill with
    neither carries no setup block. The README's install section (`README_INSTALL`) becomes the command and one
    paragraph. Each must be there exactly once."""
    command = UVX_INSTALL.format(version=version)
    line, windows = SETUP_LINE.format(version=version), SETUP_WINDOWS.format(version=version)
    out, errors = dict(tree), []
    for path, (mode, data) in sorted(tree.items()):
        if not SKILL_DOC.fullmatch(path):
            continue
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            continue  # not text: `type_errors` and the stamp refuse it
        found = (text.count(line), text.count(windows))
        if found == (0, 0):
            continue
        if found != (1, 1):
            errors.append(f"{path}: the setup block's install line and Windows sentence for {version} are not there "
                          f"once each ({found[0]} and {found[1]}), so the uvx command cannot replace them")
            continue
        out[path] = (mode, text.replace(line, command + "\n").replace(windows, "").encode("utf-8"))
    if README in tree:
        text = tree[README][1].decode("utf-8")
        sections = list(README_INSTALL.finditer(text))
        if len(sections) != 1:
            errors.append(f"{README}: the Quickstart's two install one-liners and the paragraph after them are there "
                          f"{len(sections)} times, not once, so the uvx command cannot replace them")
        else:
            section = sections[0]
            text = text[:section.start()] + README_UVX.format(command=command, version=version) + text[section.end():]
            out[README] = (tree[README][0], text.encode("utf-8"))
    return out, errors


def unlisted(tree: dict[str, tuple[str, bytes]], keys: tuple[str, ...]) -> tuple[dict[str, tuple[str, bytes]], list[str]]:
    """The tree with each of `keys` taken out of Claude's manifest, line by line so the rest stays main's, and what
    fails the build: a key that is not there exactly once as a line of its own, or a manifest that no longer reads."""
    if not keys or MANIFEST not in tree:
        return tree, []
    mode, data = tree[MANIFEST]
    text, errors = data.decode("utf-8"), []
    for key in keys:
        text, found = re.subn(rf'^[ \t]*"{re.escape(key)}":[ \t]*"[^"\n]*",[ \t]*\n', "", text, flags=re.M)
        if found != 1:
            errors.append(f"{MANIFEST}: `{key}` is there {found} times as a line of its own, not once")
    try:
        left = [key for key in keys if key in json.loads(text)]
    except ValueError as error:
        return tree, errors + [f"{MANIFEST}: without {', '.join(keys)} it does not read: {error}"]
    errors += [f"{MANIFEST}: still names `{key}`" for key in left]
    return {**tree, MANIFEST: (mode, text.encode("utf-8"))}, errors


def pipes_to_shell(tree: dict[str, tuple[str, bytes]]) -> list[str]:
    """Each download piped to a shell in the tree's text (`PIPE_TO_SHELL`)."""
    found = []
    for path, (_mode, data) in sorted(tree.items()):
        if path.lower().endswith(tuple(IMAGES)):
            continue
        text = data.decode("utf-8", errors="replace")
        found += [f"{path}: {match[0]!r} downloads and runs a script" for match in PIPE_TO_SHELL.finditer(text)]
    return found


def type_error(path: str, data: bytes) -> str | None:
    """Why claude.ai's directory refuses this file from an organization it has not verified, or None."""
    parts = path.split("/")
    name = parts[-1]
    suffix = "." + name.rsplit(".", 1)[1].lower() if "." in name.lstrip(".") else ""
    if name in HOST_CONFIGS:
        return "a hooks, MCP, LSP or monitors config; the directory's copy carries the skills alone"
    if name in PACKAGE_CONFIGS or (name.startswith("requirements") and suffix == ".txt"):
        return "a package manager's configuration"
    if ".claude-plugin" in parts[1:-1] or any(parts[i:i + 2] == [".claude", "skills"] for i in range(len(parts) - 1)):
        return "a .claude-plugin or .claude/skills folder that is not the plugin's own"
    if parts[0] == ".claude-plugin" and name != "plugin.json" and suffix not in IMAGES:
        return "only plugin.json and images go in .claude-plugin/"
    if "egress" in parts[:-1] and suffix in (".json", ".yaml", ".yml"):
        return "JSON or YAML in an egress/ folder"
    if suffix in IMAGES:
        webp = data[:4] == b"RIFF" and data[8:12] == b"WEBP"
        return None if (webp if suffix == ".webp" else data.startswith(IMAGES[suffix])) else f"not the {suffix} image its name says"
    if suffix not in TEXT_SUFFIXES and name not in TEXT_NAMES:
        return "not Markdown, text, JSON, YAML or a PNG, JPEG, GIF, WebP or ICO image"
    if data.startswith(b"#!"):
        return "starts with #!, a program"
    if b"\0" in data:
        return "has a NUL byte"
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        return "not UTF-8"
    return None


def type_errors(tree: dict[str, tuple[str, bytes]]) -> list[str]:
    """Each file of a skills-only copy that claude.ai's directory refuses from an unverified organization."""
    return [f"{path}: {reason}" for path, (_mode, data) in sorted(tree.items())
            if (reason := type_error(path, data))]


def rule_errors(tree: dict[str, tuple[str, bytes]]) -> list[str]:
    """What in the tree claude.ai's directory would hold for a reviewer or refuse."""
    errors = []
    if len(tree) > MAX_FILES:
        errors.append(f"{len(tree)} files; the directory inspects at most {MAX_FILES}")
    for path, (mode, data) in sorted(tree.items()):
        if mode == "120000":
            errors.append(f"{path}: a symlink; the directory takes regular files only")
        if data.startswith(LFS_POINTER):
            errors.append(f"{path}: a Git LFS pointer, not the file")
        image_or_font = data.startswith(IMAGE_OR_FONT) or (data[:4] == b"RIFF" and data[8:12] == b"WEBP")
        if b"\0" in data[:8192] and not image_or_font:
            errors.append(f"{path}: a binary the directory can't inspect")
        limit = MAX_FILE_BYTES if image_or_font else MAX_TEXT_BYTES
        if len(data) >= limit:
            errors.append(f"{path}: {len(data)} bytes; keep it under {limit}")
    return errors


def build(root: Path, copy: str) -> tuple[dict[str, tuple[str, bytes]], list[str], dict]:
    """A copy's tree as path -> (git mode, bytes), what breaks the directory's rules, and the manifest."""
    files, channel, skills_only, uvx, leaves_out = COPIES[copy]
    entries = tracked(root)
    chosen = {path: entry for path, entry in entries.items()
              if path in files or path.startswith(DIRECTORIES)}
    errors = [f"{path} is not tracked" for path in files if path not in chosen]
    if README not in entries:
        return {}, errors + [f"{README} is not tracked"], {}
    blobs = read_blobs(root, sorted({blob for _, blob in [*chosen.values(), entries[README]]}))
    tree = {path: (mode, blobs[blob]) for path, (mode, blob) in chosen.items()}
    try:
        manifest = json.loads(tree[MANIFEST][1]) if MANIFEST in tree else {}
    except ValueError as error:
        return tree, errors + [f"{MANIFEST}: {error}"], {}
    text = blobs[entries[README][1]].decode("utf-8")
    if skills_only:
        errors += [f"{MANIFEST} names `{field}`; this copy carries the skills alone" for field in NOT_SKILLS
                   if field in manifest]
    repository = manifest.get("repository")
    if not isinstance(repository, str) or not repository.startswith("https://github.com/"):
        return tree, errors + [f"{MANIFEST}: `repository` must be the plugin's https://github.com/ URL"], manifest
    url = repository.removesuffix("/").removesuffix(".git")
    head = git(root, "rev-parse", "HEAD").decode().strip()
    text = readme_for_tree(text, set(tree), set(entries), url, head, errors)
    tree[README] = ("100644", text.encode("utf-8"))
    version = manifest.get("version")
    if uvx:
        if isinstance(version, str) and version:
            tree, substituting = by_uvx(tree, version)
            errors += substituting + pipes_to_shell(tree)
        else:
            errors.append(f"{MANIFEST}: no `version`, so the uvx command cannot name the release")
    tree, leaving = unlisted(tree, leaves_out)
    errors += leaving
    if channel is not None:
        tree, stamping = stamped(tree, version, channel)
        errors += stamping
    return tree, errors + rule_errors(tree) + (type_errors(tree) if skills_only else []), manifest


def commit(root: Path, tree: dict[str, tuple[str, bytes]], parent: str | None, message: str) -> str:
    """Commit `tree` on `parent` and return the commit; `parent` itself when its tree is the same."""
    with tempfile.TemporaryDirectory() as scratch:
        env = {**os.environ, "GIT_INDEX_FILE": str(Path(scratch) / "index")}
        records = []
        for path, (mode, data) in sorted(tree.items()):
            blob = git(root, "hash-object", "-w", "--stdin", stdin=data).decode().strip()
            records.append(f"{mode} {blob}\t{path}\n")
        git(root, "update-index", "--add", "--index-info", stdin="".join(records).encode(), env=env)
        tree_id = git(root, "write-tree", env=env).decode().strip()
    if parent and git(root, "rev-parse", f"{parent}^{{tree}}").decode().strip() == tree_id:
        return parent
    return git(root, "commit-tree", tree_id, *(["-p", parent] if parent else []), "-m", message).decode().strip()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--check", action="store_true", help="build the tree and check it")
    action.add_argument("--commit", action="store_true", help="build, check, commit, and print the commit")
    parser.add_argument("--copy", choices=sorted(COPIES), help="the copy to commit (--check checks every copy)")
    parser.add_argument("--parent", default="", help="the branch commit to build on (none: a first commit)")
    parser.add_argument("--root", type=Path, default=REPO_ROOT, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.commit and not args.copy:
        parser.error("--commit needs --copy")

    for copy in [args.copy] if args.commit else sorted(COPIES):
        tree, errors, manifest = build(args.root, copy)
        for error in errors:
            print(f"error: {copy}: {error}", file=sys.stderr)
        if errors:
            return 1
        size = sum(len(data) for _, data in tree.values())
        print(f"The {copy} copy: {len(tree)} files, {size // 1024} KiB.", file=sys.stderr)
    if args.commit:
        source = git(args.root, "rev-parse", "HEAD").decode().strip()
        message = (f"{manifest.get('name')} {manifest.get('version')}\n\n"
                   f"The plugin's {args.copy} copy from {source}, built by Publish Release.")
        print(commit(args.root, tree, args.parent or None, message))
    return 0


if __name__ == "__main__":
    sys.exit(main())
