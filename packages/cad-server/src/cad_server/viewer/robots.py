"""A robot description resolved for the page, and the meshes cadgen made for it: what
``GET /api/v1/documents/<urdf|srdf|sdf>/<id>/structure`` and ``.../parts/<digest>`` answer.

This module is the route's decisions — what may be opened, and what the HTTP answer is.
The payload itself is cadgen's (``cad_server.robot_payload``), imported inside the handler so the
validators never load at ``cad_server.viewer`` import time; it holds each payload and primitive mesh
in this process's memory.

Two answers, both of the description at its absolute path (its document's file):

* ``structure`` -> the payload (``application/json``), every visual's mesh named by the URL
  this server answers for it: a link mesh file by its path (``/api/v1/local/files``), a
  primitive cadgen meshed by its document's ``parts/<digest>``.
* ``parts/<digest>`` -> that primitive's GLB (``model/gltf-binary``), served only when the
  description's payload names it; a mesh this process no longer holds costs one re-read of the
  description, never a 404.

Statuses, in the order they are decided: no path, a ref that is not an absolute path or
one that does not end in ``.urdf``, ``.srdf`` or ``.sdf`` -> 400; no such file -> 404; a
description cadgen cannot resolve (its validator's findings, a mesh the page cannot draw, an
SRDF with no paired URDF) -> ``RobotReadError`` (a ``ValueError``) -> 400 with the teaching
message, through the API's funnel (``{"error", "hint"}``).
"""

from __future__ import annotations

import json
import os
import re

from .backend import absolute_path
from .encoding import file_version, local_asset_url_for_path
from .scanner import node_basename

__all__ = ["ROBOT_SUFFIXES", "resolve_robot_path", "robot_response"]

ROBOT_SUFFIXES = (".urdf", ".srdf", ".sdf")
# A primitive's mesh is named by the sha256 of its GLB (``cad_server.robot_payload.primitive_glb_bytes``).
_DIGEST = re.compile(r"[0-9a-f]{64}")


def resolve_robot_path(file_ref) -> str | None:
    """The absolute description this ref names, or ``None`` for a 404.

    Raises ``ValueError`` for a ref this route will not take.
    """
    if not file_ref:
        raise ValueError("a robot is read from the absolute path of a .urdf, .srdf or .sdf")
    candidate = absolute_path(file_ref)
    if not candidate.lower().endswith(ROBOT_SUFFIXES):
        raise ValueError(
            "a robot document is a robot description; "
            f"{node_basename(candidate)} is not a {', '.join(ROBOT_SUFFIXES)} file"
        )
    return candidate if os.path.isfile(candidate) else None


def _file_url(path: str) -> str:
    """The files route's URL for a link mesh, versioned by the file's size and mtime."""
    try:
        stat_result = os.stat(path)
        version = file_version(stat_result.st_size, stat_result.st_mtime_ns)
    except OSError:
        version = ""
    return local_asset_url_for_path(path, version)


def robot_response(file_ref, mesh_ref=None, *, api="") -> tuple[int, bytes | dict, str]:
    """``(status, body, content type)``: the payload or a mesh at 200, else a JSON error dict.
    ``api`` is where the description's document is read (``kinds.document_api``): a primitive's
    mesh is its ``parts/<digest>``."""
    candidate = resolve_robot_path(file_ref)
    if candidate is None:
        return 404, {"error": f"No file at {absolute_path(file_ref)}"}, ""
    from cad_server.robot_payload import locate_robot_payload, robot_payload_bytes

    if mesh_ref is None:
        payload = json.loads(robot_payload_bytes(candidate).decode("utf-8"))
        located = locate_robot_payload(
            payload, file_url=_file_url, object_url=lambda digest: f"{api}/parts/{digest}",
        )
        return 200, json.dumps(located, separators=(",", ":")).encode("utf-8"), "application/json; charset=utf-8"

    from cad_server.robot_payload import primitive_glb_bytes

    digest = str(mesh_ref or "").strip().lower()
    if not _DIGEST.fullmatch(digest):
        raise ValueError(f"a robot's primitive mesh is named by its digest; {mesh_ref!r} is not one")
    for rebuild in (False, True):
        payload = json.loads(robot_payload_bytes(candidate, rebuild=rebuild).decode("utf-8"))
        named = {str(visual.get("mesh", {}).get("object") or "") for visual in payload.get("visuals") or []}
        if digest not in named:
            return 404, {"error": f"the robot names no mesh {digest}"}, ""
        found = primitive_glb_bytes(digest)
        if found is not None:
            return 200, found, "model/gltf-binary"
        # This process no longer holds the mesh: read the description again, which meshes it again.
    return 404, {"error": "Not found"}, ""
