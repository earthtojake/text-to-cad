"""``GET /__cad/robot``: a robot description resolved for the page, and the meshes cadgen made for it.

This module is the route's decisions — what may be opened, and what the HTTP answer is.
The payload itself is cadgen's (``cadgen.robot_payload``), imported inside the handler so the
validators never load at ``cadgen.viewer`` import time and a cache hit loads only the store.

Two answers, both named by the description's absolute path (``file``, as every file is):

* ``?file=<description>`` -> the payload (``application/json``), every visual's mesh named by
  the URL this server answers for it: a link mesh file by the asset route, a primitive cadgen
  meshed by this route with ``mesh``.
* ``?file=<description>&mesh=<object hash>`` -> that primitive's GLB (``model/gltf-binary``),
  served only when the description's payload names it; a sweep that took the object costs one
  re-read of the description, never a 404.

Statuses, in the order they are decided: no ``?file=``, a ref that is not an absolute path or
one that does not end in ``.urdf``, ``.srdf`` or ``.sdf`` -> 400; no such file -> 404; a
description cadgen cannot resolve (its validator's findings, a mesh the page cannot draw, an
SRDF with no paired URDF) -> ``RobotReadError`` (a ``ValueError``) -> 400 with the teaching
message, through the GET funnel's JSON error shape.
"""

from __future__ import annotations

import json
import os

from .backend import absolute_path
from .encoding import file_version, form_encode, local_asset_url_for_path
from .scanner import node_basename

__all__ = ["ROBOT_ROUTE_PATH", "ROBOT_SUFFIXES", "resolve_robot_path", "robot_response"]

ROBOT_ROUTE_PATH = "/__cad/robot"
ROBOT_SUFFIXES = (".urdf", ".srdf", ".sdf")


def resolve_robot_path(file_ref) -> str | None:
    """The absolute description this ref names, or ``None`` for a 404.

    Raises ``ValueError`` for a ref this route will not take.
    """
    if not file_ref:
        raise ValueError(f"GET {ROBOT_ROUTE_PATH} needs ?file=<the absolute path of a .urdf, .srdf or .sdf>")
    candidate = absolute_path(file_ref)
    if not candidate.lower().endswith(ROBOT_SUFFIXES):
        raise ValueError(
            f"{ROBOT_ROUTE_PATH} resolves robot descriptions; "
            f"{node_basename(candidate)} is not a {', '.join(ROBOT_SUFFIXES)} file"
        )
    return candidate if os.path.isfile(candidate) else None


def _file_url(path: str) -> str:
    """The asset route's URL for a link mesh, versioned by the file's size and mtime."""
    try:
        stat_result = os.stat(path)
        version = file_version(stat_result.st_size, stat_result.st_mtime_ns)
    except OSError:
        version = ""
    return local_asset_url_for_path(path, version)


def _mesh_url(description: str, digest: str) -> str:
    return f"{ROBOT_ROUTE_PATH}?{form_encode([('file', description), ('mesh', digest)])}"


def robot_response(file_ref, mesh_ref=None) -> tuple[int, bytes | dict, str]:
    """``(status, body, content type)``: the payload or a mesh at 200, else a JSON error dict."""
    candidate = resolve_robot_path(file_ref)
    if candidate is None:
        return 404, {"error": "Not found"}, ""
    from cadgen.robot_payload import locate_robot_payload, robot_payload_bytes

    if mesh_ref is None:
        payload = json.loads(robot_payload_bytes(candidate).decode("utf-8"))
        located = locate_robot_payload(
            payload, file_url=_file_url, object_url=lambda digest: _mesh_url(candidate, digest),
        )
        return 200, json.dumps(located, separators=(",", ":")).encode("utf-8"), "application/json; charset=utf-8"

    from cadgen.store.objects import is_object_hash, read_verified_object

    digest = str(mesh_ref or "").strip().lower()
    if not is_object_hash(digest):
        raise ValueError(f"{ROBOT_ROUTE_PATH} serves a primitive mesh by its object hash; {mesh_ref!r} is not one")
    for rebuild in (False, True):
        payload = json.loads(robot_payload_bytes(candidate, rebuild=rebuild).decode("utf-8"))
        named = {str(visual.get("mesh", {}).get("object") or "") for visual in payload.get("visuals") or []}
        if digest not in named:
            return 404, {"error": "Not found"}, ""
        try:
            return 200, read_verified_object(digest), "model/gltf-binary"
        except (OSError, ValueError):
            # A sweep took the object: read the description again, which meshes it again.
            continue
    return 404, {"error": "Not found"}, ""
