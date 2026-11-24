"""The CAD Viewer's Save of a model's parameters, as a test sends it: ``POST
/api/v1/documents/model/<id>/parameters`` on the engine's own server, with the page's guard header and token
(``cad_server.viewer.http_app``'s ``_parameters``), the one way the engine writes a model's parameters."""

from __future__ import annotations

import json
import urllib.error
import urllib.request


def save(ident: str, /, **values: object) -> dict:
    """``values`` saved as the Parameters tab's Save sends them: the answer (``{"id", "written", "rebuilt"}``), or
    its refusal raised as the engine raised it, ``ParameterRefused`` with the route's words (``error``),
    ``code``, ``hint`` and ``reason``, and a failed build's whole words as ``detail``."""
    from cad.engine import client
    from cad.engine.parameters import ParameterRefused

    serving = client.request({"op": "status"}, start=False)["serving"]
    token = client.request({"op": "http"}, start=False)["token"]
    request = urllib.request.Request(
        f"{serving['url']}/api/v1/documents/model/{ident}/parameters", method="POST",
        data=json.dumps({"values": values}).encode(),
        headers={"Authorization": f"Bearer {token}", "content-type": "application/json", "x-cad-viewer": "1"})
    try:
        with urllib.request.urlopen(request, timeout=600) as response:  # noqa: S310 - the test's own loopback server
            return json.loads(response.read())
    except urllib.error.HTTPError as error:
        with error:
            status, said = error.code, json.loads(error.read() or b"{}")
    if not said.get("code"):
        raise AssertionError(f"the Save was answered {status} with no refusal's code: {said}")
    refused = ParameterRefused(str(said.get("error") or ""), said["code"], said.get("hint"), said.get("reason"))
    if isinstance(said.get("detail"), str):
        refused.detail = said["detail"]  # type: ignore[attr-defined]
    raise refused
