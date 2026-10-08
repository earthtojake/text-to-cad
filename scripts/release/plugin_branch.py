#!/usr/bin/env python3
"""Build the plugin alone, as the branches installers follow take it, check it, and commit it.

Installers clone a branch and take its tree as the plugin. On `main` that tree is the
monorepo: thousands of files, a workspace npm installs, workflows and binaries that claude.ai's
directory holds for a reviewer -- and a cadgen pin from the merge on, before PyPI has the
wheel. So installers follow branches that only Publish Release writes, once the wheel is on
PyPI: one commit per release whose tree is only the plugin -- the manifests and the icon, the
MCP configs they name, `skills/`, `LICENSE`, and the README, with each link to a file outside
that tree pointed at the release commit on GitHub (CONTRIBUTING.md, "The install branches").
Two copies, differing in what they carry and the channel each config names:

- `latest`: the newest release, which every documented install command names. The copy also
  carries the marketplace catalog, which lists the plugin at the root of the branch it is read
  from, Codex's manifest and config, and the Agent Plugins standard's.
- `directory` (pushed to `claude-plugin`): claude.ai's plugin directory, which updates its
  copies.

Each MCP config names the channel its installs come from in its server's environment,
`CADGEN_INSTALL_CHANNEL`, and `CADGEN_AUTO_UPDATED=1` where a store keeps the copy up to
date (`COPIES`; cadgen's `_internal/channel.py`). A config the copy does not override keeps
main's: on `main` the Claude config names `claude-github`, and the Cursor one the Cursor
Marketplace, which reads `main`.

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

REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ".claude-plugin/plugin.json"
CATALOG = ".claude-plugin/marketplace.json"
FILES = (MANIFEST, ".claude-plugin/icon.png", ".cursor-plugin/plugin.json", "gemini-extension.json", "claude.mcp.json",
         "cursor.mcp.json", "LICENSE")
# What Claude Code's and Codex's marketplaces read besides: the catalog, and Codex's manifest and config.
MARKETPLACE_FILES = (CATALOG, ".codex-plugin/plugin.json", ".codex-plugin/logo.png", "codex.mcp.json")
# The Agent Plugins standard's manifest and server config (agent-plugins.org), which VS Code reads before
# Claude's manifest.
STANDARD_FILES = ("plugin.json", "mcp.json")


class Copy(NamedTuple):
    files: tuple[str, ...]
    # Each config's channel, and whether a store keeps its copies up to date (`CADGEN_AUTO_UPDATED`).
    channels: dict[str, tuple[str, bool]]


COPIES = {
    "latest": Copy(FILES + MARKETPLACE_FILES + STANDARD_FILES, {"cursor.mcp.json": ("cursor-github", False)}),
    "directory": Copy(FILES, {"claude.mcp.json": ("claude-directory", True), "cursor.mcp.json": ("cursor-github", False)}),
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


def with_channel(path: str, data: bytes, channel: str, auto_updated: bool, errors: list[str]) -> bytes:
    """An MCP config whose one `cadgen mcp` server names `channel` as its install channel, and
    says whether something else keeps the copy up to date."""
    try:
        config = json.loads(data)
        servers = [server for server in config["mcpServers"].values() if server["args"][-2:] == ["cadgen", "mcp"]]
    except (ValueError, KeyError, TypeError, AttributeError):
        errors.append(f"{path} is not an mcpServers config this script can read")
        return data
    if len(servers) != 1:
        errors.append(f"{path} must start exactly one `cadgen mcp` server (found {len(servers)})")
        return data
    env = {**servers[0].get("env", {}), "CADGEN_INSTALL_CHANNEL": channel}
    env.pop("CADGEN_AUTO_UPDATED", None)
    servers[0]["env"] = {**env, **({"CADGEN_AUTO_UPDATED": "1"} if auto_updated else {})}
    return json.dumps(config, indent=2, ensure_ascii=False).encode("utf-8") + b"\n"


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
    files, channels = COPIES[copy]
    entries = tracked(root)
    chosen = {path: entry for path, entry in entries.items()
              if path in files or path.startswith(DIRECTORIES)}
    errors = [f"{path} is not tracked" for path in files if path not in chosen]
    if README not in entries:
        return {}, errors + [f"{README} is not tracked"], {}
    blobs = read_blobs(root, sorted({blob for _, blob in [*chosen.values(), entries[README]]}))
    tree = {path: (mode, blobs[blob]) for path, (mode, blob) in chosen.items()}
    for path, (channel, auto_updated) in channels.items():
        if path in tree:
            tree[path] = (tree[path][0], with_channel(path, tree[path][1], channel, auto_updated, errors))
    try:
        manifest = json.loads(tree[MANIFEST][1]) if MANIFEST in tree else {}
    except ValueError as error:
        return tree, errors + [f"{MANIFEST}: {error}"], {}
    repository = manifest.get("repository")
    if not isinstance(repository, str) or not repository.startswith("https://github.com/"):
        return tree, errors + [f"{MANIFEST}: `repository` must be the plugin's https://github.com/ URL"], manifest
    url = repository.removesuffix("/").removesuffix(".git")
    head = git(root, "rev-parse", "HEAD").decode().strip()
    text = readme_for_tree(blobs[entries[README][1]].decode("utf-8"), set(tree), set(entries), url, head, errors)
    tree[README] = ("100644", text.encode("utf-8"))
    return tree, errors + rule_errors(tree), manifest


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
