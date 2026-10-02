#!/usr/bin/env python3
"""Build the plugin ZIP that OpenAI's plugin submission portal takes, and check it.

The portal (https://platform.openai.com/plugins) is a web page with no API, so a
release cannot submit the plugin itself. It can hand the person who does a file
that uploads cleanly. Publish Release builds that file from the release commit,
before any irreversible step, and attaches it to the GitHub Release.

The plugin is at the archive's root, where the portal looks for it: the Codex
manifest and the rest of `.codex-plugin/`, `skills/`, `LICENSE`, and every file
the manifest points at, each folder with an entry of its own. (The portal also
documents a single top-level folder, but turned 0.7.6's away -- a folder with no
directory entry of its own -- as having no plugin at all.) One thing differs from the checkout: the portal requires
that `mcpServers` "must resolve to the root `.mcp.json`". A server config kept
under another name (a root `.mcp.json` is one Claude Code would load too) goes
into the archive as `.mcp.json`, and the archived manifest points there.

The checks are the package rules the portal documents, named by its error codes
(https://developers.openai.com/plugins/deploy/submission-errors). Listing limits
are the final-submission ones, such as 30 characters for the name and subtitle,
not the looser upload ones: a ZIP that uploads but cannot be submitted is not
ready. The portal's own skill and policy scans still run after the upload.

    scripts/release/plugin_zip.py --out PATH   # build, check, write
    scripts/release/plugin_zip.py --check      # build and check only
"""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import re
import struct
import subprocess
import sys
import zipfile

REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ".codex-plugin/plugin.json"
ROOTS = (".codex-plugin", "skills", "LICENSE")
MCP_CONFIG = ".mcp.json"
ICONS = ("logo", "logoDark", "composerIcon", "composerIconDark")
SEMVER = re.compile(r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(-[0-9A-Za-z.-]+)?(\+[0-9A-Za-z.-]+)?")
# A clone without git-lfs (CI's included) checks LFS-tracked files out as pointers.
LFS_POINTER = b"version https://git-lfs.github.com/spec/v1"
MIB = 1024 * 1024


class Package:
    """The archive's files by plugin-relative path, and what the checks found."""

    def __init__(self, manifest: dict, errors: list[str] | None = None) -> None:
        self.manifest = manifest
        self.files: dict[str, tuple[bytes, bool]] = {}  # path -> (bytes, executable)
        self.icons: list[str] = []
        self.errors: list[str] = errors or []
        self.warnings: list[str] = []

    @property
    def top(self) -> str:
        name = self.manifest.get("name")
        return name if isinstance(name, str) and name else "plugin"


def tracked_modes(root: Path) -> dict[str, str]:
    """Every tracked path of the checkout, with its git mode (120000 is a symlink)."""
    listing = subprocess.run(["git", "-C", str(root), "ls-files", "-z", "-s"],
                             check=True, capture_output=True).stdout.decode("utf-8")
    modes = {}
    for record in filter(None, listing.split("\0")):
        meta, path = record.split("\t", 1)
        modes[path] = meta.split()[0]
    return modes


def manifest_path(package: Package, name: str, value: object) -> str | None:
    """The archive path a manifest field names, or None after recording why it names none."""
    if not isinstance(value, str) or not value.startswith("./"):
        package.errors.append(f"branding_asset_path_missing_root_prefix: {name} must be a path "
                              f"starting with ./ (got {value!r})")
        return None
    path = value[2:].rstrip("/")
    if not path or ".." in path.split("/") or "\\" in path:
        package.errors.append(f"declared_asset_path_unsafe: {name} must name a file inside the plugin "
                              f"(got {value!r})")
        return None
    return path


def collect(root: Path) -> Package:
    modes = tracked_modes(root)
    if MANIFEST not in modes:
        return Package({}, errors=[f"plugin_manifest_missing: {MANIFEST} is not tracked"])
    try:
        manifest = json.loads((root / MANIFEST).read_text(encoding="utf-8"))
    except ValueError as error:
        return Package({}, errors=[f"plugin_manifest_json_malformed: {MANIFEST}: {error}"])
    if not isinstance(manifest, dict):
        return Package({}, errors=[f"plugin_manifest_root_not_object: {MANIFEST}"])
    package = Package(manifest)
    wanted = {path for path in modes if path in ROOTS or path.startswith(tuple(f"{r}/" for r in ROOTS))}
    sources = {}  # archive path -> checkout path, where they differ

    if manifest.get("skills") not in ("./skills/", "./skills"):
        package.errors.append("plugin_skills_path_unsupported: `skills` must resolve to the root skills/ directory")
    for name in ("apps", "hooks"):
        if name in manifest:
            package.errors.append(f"{name}: plugin ZIPs with app references or lifecycle hooks "
                                  "cannot currently be submitted")

    if "mcpServers" in manifest:
        source = manifest_path(package, "mcpServers", manifest["mcpServers"])
        if source and source not in modes:
            package.errors.append(f"plugin_mcp_file_missing: mcpServers names {source}, which is not tracked")
        elif source == MCP_CONFIG:
            wanted.add(source)
        elif source:
            sources[MCP_CONFIG] = source
            wanted.discard(source)
            package.manifest = manifest = {**manifest, "mcpServers": f"./{MCP_CONFIG}"}

    interface = manifest.get("interface") if isinstance(manifest.get("interface"), dict) else {}
    declared = [(f"interface.{name}", interface[name]) for name in ICONS if name in interface]
    declared += [(f"interface.screenshots[{index}]", value)
                 for index, value in enumerate(interface.get("screenshots") or [])]
    for name, value in declared:
        path = manifest_path(package, name, value)
        if path and path not in modes:
            package.errors.append(f"declared_asset_file_missing: {name} names {path}, which is not tracked")
        elif path:
            wanted.add(path)
            if name.split(".")[1] in ICONS and path not in package.icons:
                package.icons.append(path)

    extensions = manifest.get("extensions") if isinstance(manifest.get("extensions"), dict) else {}
    openai = extensions.get("com.openai") if isinstance(extensions.get("com.openai"), dict) else {}
    if "onboardingSkill" in openai:
        value = openai["onboardingSkill"]
        if not (isinstance(value, str) and re.fullmatch(r"\./skills/[^/]+/SKILL\.md", value)
                and value[2:] in modes):
            package.errors.append("extensions.com.openai.onboardingSkill must be the ./skills/<name>/SKILL.md "
                                  f"path of a packaged skill (got {value!r})")

    for archived in sorted(wanted | sources.keys()):
        source = sources.get(archived, archived)
        mode = modes[source]
        if mode not in ("100644", "100755"):
            package.errors.append(f"archive_member_type_unsupported: {source} has git mode {mode}; "
                                  "only regular files can ship")
            continue
        try:
            data = (root / source).read_bytes()
        except FileNotFoundError:
            package.errors.append(f"{source} is tracked but missing from the checkout")
            continue
        if data.startswith(LFS_POINTER):
            package.errors.append(f"{source} is a Git LFS pointer, not the file; keep plugin files out of LFS")
            continue
        if archived == MCP_CONFIG:
            data = listed_install(package, data)
        package.files[archived] = (data, mode == "100755")
    if sources:
        package.files[MANIFEST] = (json.dumps(manifest, indent=2, ensure_ascii=False).encode("utf-8") + b"\n",
                                   False)
    return package


def listed_install(package: Package, data: bytes) -> bytes:
    """The server config with `cadgen mcp --install store`, so CAD's analytics can tell a directory
    install from a manual one (their `source`). It decides nothing: every install is asked first."""
    try:
        config = json.loads(data)
        servers = config["mcpServers"]
        stamped = 0
        for server in servers.values():
            args = server.get("args")
            if isinstance(args, list) and args[-2:] == ["cadgen", "mcp"]:
                server["args"] = [*args, "--install", "store"]
                stamped += 1
    except (ValueError, KeyError, TypeError, AttributeError):
        package.errors.append(f"{MCP_CONFIG} is not an mcpServers config this script can read")
        return data
    if stamped != 1:
        package.errors.append(f"{MCP_CONFIG} must start exactly one `cadgen mcp` server (found {stamped})")
    return json.dumps(config, indent=2).encode("utf-8") + b"\n"


def check_manifest(package: Package) -> None:
    manifest, errors = package.manifest, package.errors

    def text(name: str, value: object, limit: int | None, code: str) -> None:
        if not isinstance(value, str) or not value.strip():
            errors.append(f"{code}_missing: {name} is required")
        elif limit is not None and len(value) > limit:
            errors.append(f"{code}_too_long: {name} is {len(value)} characters; the directory allows {limit}")

    name = manifest.get("name")
    if not (isinstance(name, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", name)):
        errors.append("plugin_name_format: `name` must be at most 64 ASCII letters, digits, `_` or `-`, "
                      "starting with a letter or digit")
    if not (isinstance(manifest.get("version"), str) and SEMVER.fullmatch(manifest["version"])):
        errors.append("plugin_version_not_semver: `version` must use semantic versioning, such as 1.0.0")
    text("description", manifest.get("description"), 1024, "plugin_description")
    author = manifest.get("author") if isinstance(manifest.get("author"), dict) else {}
    text("author.name", author.get("name"), 120, "plugin_author_name")

    interface = manifest.get("interface")
    if not isinstance(interface, dict):
        errors.append("plugin_interface_wrong_type: the Codex format requires an `interface` object")
        return
    for key, limit in (("displayName", 30), ("shortDescription", 30), ("longDescription", 4000),
                       ("developerName", 80), ("category", None)):
        text(f"interface.{key}", interface.get(key), limit,
             "plugin_" + re.sub(r"(?<!^)(?=[A-Z])", "_", key).lower())
    capabilities = interface.get("capabilities")
    if not (isinstance(capabilities, list) and all(isinstance(item, str) and item for item in capabilities)):
        errors.append("plugin_capabilities_wrong_type: interface.capabilities must be a list of strings")
    elif len(capabilities) > 20:
        errors.append("plugin_capabilities_too_many: interface.capabilities allows 20 entries")
    prompts = interface.get("defaultPrompt", [])
    prompts = [prompts] if isinstance(prompts, str) else prompts
    if not isinstance(prompts, list) or len(prompts) > 3:
        errors.append("plugin_default_prompt_too_many: interface.defaultPrompt allows three prompts")
    else:
        for index, prompt in enumerate(prompts, 1):
            if not isinstance(prompt, str) or not prompt.strip():
                errors.append(f"plugin_default_prompt_empty: starter prompt {index} must be text")
            elif len(prompt) > 128:
                errors.append(f"plugin_default_prompt_too_long: starter prompt {index} is {len(prompt)} "
                              "characters; the directory allows 128")
    for key in ("logo", "composerIcon"):
        if key not in interface:
            code = "plugin_" + re.sub(r"(?<!^)(?=[A-Z])", "_", key).lower()
            package.warnings.append(f"{code}_path_missing: the portal requires interface.{key} "
                                    "(a square image) before it accepts a Codex-format package")


def front_matter(data: bytes) -> tuple[dict[str, str], str] | None:
    """A SKILL.md's top-level `key: value` front-matter fields and its body."""
    block = re.match(r"---\n(?:(.*?)\n)?---[ \t]*(?:\n|$)", data.decode("utf-8"), re.S)
    if block is None:
        return None
    fields = {}
    for line in (block[1] or "").splitlines():
        if match := re.match(r"([A-Za-z_][\w-]*):\s*(.*)$", line):
            value = match[2].strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
                value = value[1:-1]
            fields[match[1]] = value
    return fields, block.string[block.end():]


def check_skills(package: Package) -> None:
    errors, seen = package.errors, set()
    package.warnings.extend(f"skill_file_ignored: {path} sits directly under skills/, so it is not a skill"
                            for path in package.files if re.fullmatch(r"skills/[^/]+", path))
    for directory in sorted({path.split("/")[1] for path in package.files if re.match(r"skills/[^/]+/", path)}):
        path = f"skills/{directory}/SKILL.md"
        if directory.startswith("."):
            errors.append(f"skill_directory_hidden: skills/{directory} begins with a dot")
        if path not in package.files:
            errors.append(f"skill_manifest_missing: {path}")
            continue
        parsed = front_matter(package.files[path][0])
        if parsed is None:
            errors.append(f"skill_frontmatter_missing: {path} must start with YAML front matter between ---")
            continue
        fields, body = parsed
        name, description = fields.get("name", ""), fields.get("description", "")
        if not name:
            errors.append(f"skill_name_missing: {path}")
        if not description:
            errors.append(f"skill_description_missing: {path}")
        elif len(description) > 1024:
            errors.append(f"skill_description_too_long: {path} description is {len(description)} characters")
        if not body.strip():
            errors.append(f"skill_body_empty: {path}")
        if len(f"{package.top}:{name}") > 64:
            errors.append(f"skill_identity_too_long: {package.top}:{name} is over 64 characters")
        if name and name in seen:
            errors.append(f"skill_identity_duplicate: more than one skill is named {name}")
        seen.add(name)


def check_images(package: Package) -> None:
    for path in package.icons:
        data = package.files.get(path, (b"", False))[0]
        suffix = Path(path).suffix.lower()
        if suffix not in (".png", ".jpg", ".jpeg", ".webp", ".svg"):
            package.errors.append(f"image_file_format_unsupported: {path}")
        elif len(data) > 5 * MIB:
            package.errors.append(f"image_file_too_large: {path} is over 5 MiB")
        elif suffix == ".png":
            if data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
                package.errors.append(f"raster_image_decode_failed: {path} is not a PNG")
                continue
            width, height = struct.unpack(">II", data[16:24])
            if width != height:
                package.errors.append(f"raster_image_not_square: {path} is {width}x{height}")
            elif not 48 <= width <= 4096:
                package.errors.append(f"raster_image_dimensions: {path} is {width}x{height}; "
                                      "icons are 48 to 4096 pixels square")


def check_archive(package: Package) -> None:
    entries = {path: len(data) for path, (data, _) in package.files.items()}
    if len(entries) > 5000:
        package.errors.append(f"archive_too_many_entries: {len(entries)} entries; the limit is 5,000")
    if sum(entries.values()) > 512 * MIB:
        package.errors.append("archive_uncompressed_too_large: the extracted archive exceeds 512 MiB")
    for path, size in entries.items():
        if size > 100 * MIB:
            package.errors.append(f"archive_member_too_large: {path} exceeds 100 MiB")
        if len(path.split("/")) > 20:
            package.errors.append(f"archive_member_path_too_deep: {path} has more than 20 segments")
        if "\\" in path or path != path.strip():
            package.errors.append(f"archive_member_path: {path} has a backslash or outer whitespace")
    package.errors.extend(f"archive_member_path_normalization_collision: {path}"
                          for path, count in Counter(path.lower() for path in entries).items() if count > 1)


def build(root: Path = REPO_ROOT, out: Path | None = None) -> Package:
    package = collect(root)
    if package.manifest:
        check_manifest(package)
        check_skills(package)
        check_images(package)
        check_archive(package)
    if out is None or package.errors:
        return package
    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as archive:
        for folder in sorted(folders(package.files)):
            info = zipfile.ZipInfo(f"{folder}/", date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = (0o40755 << 16) | 0x10
            archive.writestr(info, b"")
        for path, (data, executable) in sorted(package.files.items()):
            info = zipfile.ZipInfo(path, date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (0o100755 if executable else 0o100644) << 16
            archive.writestr(info, data)
    if out.stat().st_size > 100 * 1000 * 1000:
        package.errors.append("archive_too_large: the compressed ZIP exceeds 100 MB")
        out.unlink()
    return package


def folders(files) -> set[str]:
    """Every folder that holds a file of the archive, nested ones included."""
    return {"/".join(path.split("/")[:depth]) for path in files for depth in range(1, path.count("/") + 1)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--out", type=Path, help="write the checked ZIP here")
    mode.add_argument("--check", action="store_true", help="build and check without writing")
    args = parser.parse_args(argv)
    package = build(REPO_ROOT, args.out)
    for warning in package.warnings:
        print(f"warning: {warning}", file=sys.stderr)
    for error in package.errors:
        print(f"error: {error}", file=sys.stderr)
    if package.errors:
        return 1
    where = args.out if args.out else "plugin ZIP check"
    print(f"{where}: {len(package.files)} files at the root, "
          f"{sum(len(data) for data, _ in package.files.values())} bytes before compression")
    return 0


if __name__ == "__main__":
    sys.exit(main())
