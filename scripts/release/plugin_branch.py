#!/usr/bin/env python3
"""Build the plugin that claude.ai's plugin directory follows, check it, and commit it.

The repository root is the plugin for every installer that clones it, but
claude.ai's directory treats the folder it follows as the whole plugin: there the
monorepo's thousands of files, its workflows, lockfile and binaries are policy
holds, and every install copies all of them. So the directory follows the
`plugin` branch instead: one commit per release whose tree is only the plugin --
the Claude, Cursor and Gemini manifests and the icon, the MCP config they name,
`skills/`, `LICENSE`, and the README, with each link to a file outside that tree
pointed at the release commit on GitHub. Every other store installs from `main`
or the GitHub Release (CONTRIBUTING.md, "The plugin branch").

The checks are claude.ai's file rules, the strictest of the directories
(https://claude.com/docs/plugins/pre-submission-checklist.md): a tree that breaks
one is held for a reviewer, or never validates. Publish Release runs `--check`
before anything irreversible and, on main, commits the tree onto `plugin` and
pushes it. Never commit to that branch by hand.

    scripts/release/plugin_branch.py --check
    scripts/release/plugin_branch.py --commit [--parent REF]   # prints the commit
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

REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ".claude-plugin/plugin.json"
FILES = (MANIFEST, ".claude-plugin/icon.png", ".cursor-plugin/plugin.json", "gemini-extension.json", "claude.mcp.json",
         "LICENSE")
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


def build(root: Path) -> tuple[dict[str, tuple[str, bytes]], list[str], dict]:
    """The plugin tree as path -> (git mode, bytes), what breaks the directory's rules, and the manifest."""
    entries = tracked(root)
    chosen = {path: entry for path, entry in entries.items()
              if path in FILES or path.startswith(DIRECTORIES)}
    errors = [f"{path} is not tracked" for path in FILES if path not in chosen]
    if README not in entries:
        return {}, errors + [f"{README} is not tracked"], {}
    blobs = read_blobs(root, sorted({blob for _, blob in [*chosen.values(), entries[README]]}))
    tree = {path: (mode, blobs[blob]) for path, (mode, blob) in chosen.items()}
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
    parser.add_argument("--parent", default="", help="the plugin branch commit to build on (none: a first commit)")
    parser.add_argument("--root", type=Path, default=REPO_ROOT, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    tree, errors, manifest = build(args.root)
    for error in errors:
        print(f"error: {error}", file=sys.stderr)
    if errors:
        return 1
    size = sum(len(data) for _, data in tree.values())
    print(f"Plugin tree: {len(tree)} files, {size // 1024} KiB.", file=sys.stderr)
    if args.commit:
        source = git(args.root, "rev-parse", "HEAD").decode().strip()
        message = f"{manifest.get('name')} {manifest.get('version')}\n\nThe plugin from {source}, built by Publish Release."
        print(commit(args.root, tree, args.parent or None, message))
    return 0


if __name__ == "__main__":
    sys.exit(main())
