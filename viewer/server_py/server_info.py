"""Builds the /__cad/server payload (app id, dynamicRoot, serverFeatures, etc.)
that the CAD Viewer client consumes. The optional serverMode key is omitted when
empty.
"""

from __future__ import annotations

import os

from .paths import filesystem_path_from_url_path

VIEWER_SERVER_APP_ID = "cad-viewer"
DEFAULT_VIEWER_HOST = "127.0.0.1"
DEFAULT_VIEWER_PORT = 3245


def normalize_viewer_port(value, fallback=DEFAULT_VIEWER_PORT) -> int:
    try:
        parsed = int(str(value if value is not None else ""))
    except (TypeError, ValueError):
        return fallback
    return parsed if 0 < parsed <= 65535 else fallback


def _resolve_view_root(root_dir: str) -> dict:
    """The requested directory, absolute. Empty means the process cwd — the same
    fallback the backend applies, since a request's URL path IS its directory.

    Routed through the URL-path reader for the same reason `LocalAssetBackend.resolve_root`
    is:
    a Windows directory arrives as `/D:/models`, which abspath alone turns into
    `C:\\D:\\models`."""
    resolved = os.path.abspath(filesystem_path_from_url_path(str(root_dir or "").strip()) or os.getcwd())
    return {"dir": resolved, "rootPath": resolved, "rootName": os.path.basename(resolved)}


def build_viewer_server_info(
    *,
    root_dir: str = "",
    port: int = DEFAULT_VIEWER_PORT,
    pid: int | None = None,
    host: str = DEFAULT_VIEWER_HOST,
    backend: str = "local-fs",
    step_artifact_generation_available: bool = True,
    viewer_version: str = "",
    server_mode: str = "",
    server_features=None,
) -> dict:
    view_root = _resolve_view_root(root_dir)
    normalized_port = normalize_viewer_port(port)
    normalized_mode = str(server_mode or "").strip()
    info = {
        "app": VIEWER_SERVER_APP_ID,
        "viewerVersion": str(viewer_version or ""),
    }
    if normalized_mode:
        info["serverMode"] = normalized_mode
    info["serverFeatures"] = [str(f or "").strip() for f in (server_features or []) if str(f or "").strip()]
    info["backend"] = backend
    info["rootDir"] = view_root["dir"]
    info["rootPath"] = view_root["rootPath"]
    info["rootName"] = view_root["rootName"]
    info["port"] = normalized_port
    info["pid"] = pid if isinstance(pid, int) else os.getpid()
    info["stepArtifactGenerationAvailable"] = step_artifact_generation_available is not False
    info["url"] = f"http://{host}:{normalized_port}"
    return info
