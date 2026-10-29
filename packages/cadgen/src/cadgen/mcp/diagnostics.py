"""Best-effort inventory of supported user-level CAD host configurations and plugin pins.

This adapter never executes a host or exposes raw configuration. Cached plugins are evidence
of files, never proof that a host has loaded that version.
"""
from __future__ import annotations

import os
import sys
from itertools import islice
from pathlib import Path

from cadgen._internal.doctor_files import MAX_BYTES, _port, read
from cadgen._internal.installations import VERSION

LIMIT = 64
COVERAGE = ("User-level Codex config and cached text-to-cad plugins, Claude Code installed-plugin registry, "
            "Claude Desktop config, Cursor local plugins and Gemini extensions. Project/workspace configs, "
            "other profiles, remote hosts, loose skills and Grok-specific storage are not inspected. "
            "Cached or registered plugins may not be enabled or loaded by a running host.")



def _server(entry: dict) -> dict:
    """Only cadgen version and selected port are allowed out of launch config."""
    arguments = entry.get("args", [])
    arguments = arguments if isinstance(arguments, list) and all(isinstance(a, str) for a in arguments) else []
    environment = entry.get("env")
    environment = environment if isinstance(environment, dict) else {}
    named = environment.get("CADGEN_INSTALLATION_VERSION")
    named = named if isinstance(named, str) and VERSION.fullmatch(named) else None
    pin = None
    for argument in arguments:
        if argument.startswith("cadgen==") and VERSION.fullmatch(argument[8:]):
            pin = pin or argument[8:]
        elif argument.startswith("+") and VERSION.fullmatch(argument[1:]):
            named = named or argument[1:]
    raw_port = environment.get("CADGEN_PORT")
    legacy_port = raw_port is None and "CADGEN_ENGINE_PORT" in environment
    port = None if legacy_port else 3245 if raw_port is None else _port(raw_port)
    # Argparse accepts both spellings; do not mistake a retired environment selection for default.
    for index, argument in enumerate(arguments):
        if argument == "--port":
            port = _port(arguments[index + 1]) if index + 1 < len(arguments) else None
            legacy_port = False
        elif argument.startswith("--port="):
            port = _port(argument.partition("=")[2])
            legacy_port = False
    result = {"release": pin, "port": port, "status": "ok" if (pin or named) and port else "unknown"}
    if named:
        result["installation"] = named
    if legacy_port:
        result["port_status"] = "unsupported_legacy_variable"
    return result


def _servers(provider: str, path: Path, data: dict, key: str, kind: str) -> list[dict]:
    entries = data.get(key, {})
    if not isinstance(entries, dict):
        return [{"provider": provider, "path": str(path), "kind": kind, "status": "invalid"}]
    found = []
    for name, entry in islice(entries.items(), LIMIT):
        if not isinstance(entry, dict):
            continue
        arguments = entry.get("args", [])
        command = entry.get("command", "")
        is_cad = name in {"cad", "cad-dev", "text-to-cad"} or (
            isinstance(command, str) and "cadgen" in Path(command).name) or (
            isinstance(arguments, list) and any(isinstance(a, str) and (a.startswith("cadgen==")
                                                or a in {"cadgen", "cadgen.cli"}) for a in arguments))
        if is_cad:
            found.append({"provider": provider, "path": str(path), "kind": kind, **_server(entry)})
    return found


def _config(provider: str, path: Path, key: str = "mcpServers", *, toml: bool = False,
            kind: str = "config") -> list[dict]:
    data, status = read(path, toml=toml)
    if data is None:
        return [{"provider": provider, "path": str(path), "kind": kind, "status": status}]
    return _servers(provider, path, data, key, kind) or [
        {"provider": provider, "path": str(path), "kind": kind, "status": "no_cad_entry"}]


def _plugin(provider: str, root: Path, kind: str) -> list[dict]:
    # Manifests point to one adjacent MCP file, or Gemini keeps its servers inline.
    manifest = root / {"codex": ".codex-plugin/plugin.json", "cursor": ".cursor-plugin/plugin.json",
                       "gemini": "gemini-extension.json"}.get(provider, ".claude-plugin/plugin.json")
    data, status = read(manifest)
    if data is None:
        return [{"provider": provider, "path": str(manifest), "kind": kind, "status": status}]
    if data.get("name") != "text-to-cad":
        return []
    servers = data.get("mcpServers")
    if isinstance(servers, dict):
        found = _servers(provider, manifest, data, "mcpServers", kind)
    elif isinstance(servers, str) and servers.startswith("./") and ".." not in Path(servers).parts:
        found = _config(provider, root / servers, kind=kind)
    else:
        found = [{"provider": provider, "path": str(manifest), "kind": kind, "status": "unknown"}]
    version = data.get("version")
    for item in found:
        item["manifest"] = str(manifest)
        if isinstance(version, str) and VERSION.fullmatch(version):
            item["plugin_version"] = version
    return found


def _children(path: Path) -> tuple[list[Path], str]:
    try:
        with os.scandir(path) as entries:
            found = list(islice(entries, LIMIT + 1))
        return [Path(entry.path) for entry in found[:LIMIT] if entry.is_dir()], (
            "limited" if len(found) > LIMIT else "ok")
    except FileNotFoundError:
        return [], "missing"
    except OSError:
        return [], "unreadable"


def inventory() -> dict:
    home = Path.home()
    codex = Path(os.environ.get("CODEX_HOME") or home / ".codex")
    claude = Path(os.environ.get("CLAUDE_CONFIG_DIR") or home / ".claude")
    if sys.platform == "darwin":
        desktop = home / "Library/Application Support/Claude/claude_desktop_config.json"
    elif sys.platform == "win32":
        desktop = Path(os.environ.get("APPDATA") or home / "AppData/Roaming") / "Claude/claude_desktop_config.json"
    else:
        desktop = home / ".config/Claude/claude_desktop_config.json"
    desktop = Path(os.environ.get("CLAUDE_DESKTOP_CONFIG") or desktop)
    found = _config("codex", codex / "config.toml", "mcp_servers", toml=True)
    found += _config("claude-desktop", desktop)
    # Claude's install registry is authoritative about paths, but not the running process.
    registry = claude / "plugins/installed_plugins.json"
    data, status = read(registry)
    if data is None:
        found.append({"provider": "claude", "path": str(registry), "kind": "registry", "status": status})
    elif isinstance(data.get("plugins"), dict):
        remaining = LIMIT
        for name, entries in islice(data["plugins"].items(), LIMIT):
            if name.split("@", 1)[0] != "text-to-cad":
                continue
            if not isinstance(entries, list):
                found.append({"provider": "claude", "path": str(registry), "kind": "registry", "status": "invalid"})
                continue
            if len(entries) > remaining:
                found.append({"provider": "claude", "path": str(registry), "kind": "registry", "status": "limited"})
            for entry in entries[:remaining]:
                remaining -= 1
                if isinstance(entry, dict) and isinstance(entry.get("installPath"), str):
                    items = _plugin("claude", Path(entry["installPath"]), "registered_plugin")
                    for item in items:
                        item["registry"] = str(registry)
                    found += items
    else:
        found.append({"provider": "claude", "path": str(registry), "kind": "registry", "status": "invalid"})
    # Cache versions are not inferred to be active. No recursive disk or environment scan.
    cache = codex / "plugins/cache"
    marketplaces, state = _children(cache)
    if state != "ok":
        found.append({"provider": "codex", "path": str(cache), "kind": "cache", "status": state})
    remaining = LIMIT
    for marketplace in marketplaces:
        versions, state = _children(marketplace / "text-to-cad")
        if state in {"limited", "unreadable"}:
            found.append({"provider": "codex", "path": str(marketplace / "text-to-cad"), "kind": "cache", "status": state})
        if len(versions) > remaining:
            found.append({"provider": "codex", "path": str(cache), "kind": "cache", "status": "limited"})
        for root in versions[:remaining]:
            remaining -= 1
            found += _plugin("codex", root, "cached_plugin")
    for provider, folder in (("cursor", home / ".cursor/plugins/local"), ("gemini", home / ".gemini/extensions")):
        children, state = _children(folder)
        if state != "ok":
            found.append({"provider": provider, "path": str(folder), "kind": "plugins", "status": state})
        for root in children:
            if root.name == "text-to-cad":
                found += _plugin(provider, root, "local_plugin")
    return {"coverage": COVERAGE, "sources": found}
