"""The update's handshake between releases, frozen (``update_handshake.json``).

Nothing on a device compares versions any more: an update is release A's engine running release B's
code, and B's reading what A wrote. A's engine runs B's ``setup --engine-update`` and reads its
progress frames; A's helper starts B's engine with B's Python by the daemon module's name, asks it
``status`` and ``http``, stops it with ``stop`` (``drain``), and runs the release it leaves current's
``plugin --refresh`` (the plugin folder following it); B reads the ``current`` file, the installation
records, the release folders, the token and the switch's record that A wrote. And across the
update, what A's pages and a host's kept card shell read of B's engine over HTTP (``http``): the
page a tab is at (``/<id>``), the CAD app's module a kept shell imports (``/app``), and
``GET /api/v1/server``'s ``release`` and ``instance`` (with ``notice`` and ``update``), which a page
reloads on and a card follows its update by. So all of
it must stay as it is across releases, and this test fails when any of it changes: a change here is
one made on purpose, for every release still installed, never one made in passing. Change the golden
file with it, and say in the change why releases before it still update.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from tests.python.support import engine_daemon
from tests.python.support.paths import add_repo_path

add_repo_path("packages/cad/src")

GOLDEN = Path(__file__).with_name("update_handshake.json")


class Started(Exception):
    """What the patched ``Popen`` raises: nothing is started."""


def _flags(parser) -> list[str]:
    return sorted(option for action in parser._actions for option in action.option_strings)


def _ask(app, path: str) -> tuple[int, str, bytes]:
    """``app``'s answer to ``GET path``, in process: its status, its content type and its body."""
    from cad_server.mcp.tunnel import _CapturedHandler
    from cad_server.viewer.response import Request, Response

    handler = _CapturedHandler()
    app.handle(Request(raw_method="GET", path=path, query=[], headers={}, read_body=lambda: b""), Response(handler))
    return handler.status, handler.headers.get("content-type", ""), handler.wfile.getvalue()


def http_surface() -> dict:
    """What a page or a kept card shell of one release reads of another release's engine over HTTP."""
    import tempfile

    from cad_server.mcp import tunnel
    from cad_server.viewer.http_app import create_cad_app

    with tempfile.TemporaryDirectory() as dist:
        Path(dist, "index.html").write_text("<!doctype html><title>page</title>", encoding="utf-8")
        app = create_cad_app(host="127.0.0.1", port=0, dist_dir=dist)
        status, kind, body = _ask(app, "/api/v1/server")
        server = json.loads(body) if status == 200 else {}
        page = _ask(app, "/6f1c2a4e-1b2c-5d3e-8f4a-0123456789ab")
        module = _ask(app, tunnel._APP_ROUTE)
    # The CAD app's module is the route's whether or not this install has a build of it: never the page.
    routed = module[1].startswith("text/javascript") or (
        module[0] == 404 and json.loads(module[2]).get("error") == "this install has no CAD app build")
    return {
        "server": {"route": "/api/v1/server", "status": status, "type": kind,
                   "keys": sorted(key for key in ("instance", "notice", "release", "update") if key in server)},
        "page": {"route": "/<id>", "status": page[0], "type": page[1]},
        "app": {"route": tunnel._APP_ROUTE, "routed": routed},
    }


def surface() -> dict:
    """The handshake as this source tree has it."""
    from cad_server._internal import installations, releases, switch, update
    from cad_server.cli import plugin as plugin_cli
    from cad_server.cli import setup as setup_cli
    from cad_server.cli import update as update_cli
    from cad.engine import client, places, progress
    from cad_server.engine import daemon, registry
    from cad_server.viewer.engine_app import EngineApp

    # A client of one release starting the current installation's engine: its Python, these arguments.
    current = {"python": "PYTHON", "prefix": os.path.abspath("elsewhere"), "version": "9.9.9"}
    with mock.patch.object(places, "engine", lambda: current), \
            mock.patch.object(subprocess, "Popen", side_effect=Started) as popen:
        try:
            client._start()
        except Started:
            pass
    started = popen.call_args.args[0]

    # The engine's answers the helper reads.
    engine = daemon.Daemon(cap=1)
    try:
        status: list[dict] = []
        engine.handle({"op": "status"}, status.append)
        stopped: list[dict] = []
        engine.handle({"op": "stop", "drain": True}, stopped.append)
    finally:
        engine.supervisor.stop()
    endpoint = EngineApp.endpoint(SimpleNamespace(server=SimpleNamespace(url="URL", port=1), token="TOKEN"))

    # What A writes and B reads.
    state = installations.state()
    root = Path(state.path(installations.FOLDER)).parent
    folder = releases.where("9.9.9")
    python, console = releases.base.interpreter(folder), releases.console(folder)
    python.parent.mkdir(parents=True, exist_ok=True)
    for path in (python, console):
        path.write_text("", encoding="utf-8")
    installations.register("9.9.9", (str(console), str(python), str(folder)))
    installations.point("9.9.9")
    record = json.loads((root / installations.FOLDER / "9.9.9.json").read_text(encoding="utf-8"))
    frame = progress.event("update", "build123d", job="9.9.9", detail="d", done=1, total=4)
    # What the helper runs of the release it leaves current: its own plugin folder's refresh.
    with mock.patch.object(subprocess, "run", side_effect=Started) as run:
        try:
            switch.follow(told=lambda _line: None)
        except Started:
            pass
    return {
        "setup": {"command": "setup", "engine_update_flag": "--engine-update",
                  "flags": _flags(setup_cli.build_parser())},
        "update": {"command": "update", "flags": _flags(update_cli.build_parser())},
        "plugin": {"arguments": run.call_args.args[0][1:], "flags": _flags(plugin_cli.build_parser())},
        "progress": {"line": sorted({"progress": frame}), "frame": sorted(frame), "kind": frame["kind"],
                     "stages": list(update.STAGES)},
        "daemon": {"arguments": started[1:], "module": client.DAEMON_MODULE},
        "http": http_surface(),
        "ops": {"status": sorted(key for key in ("ok", "pid", "prefix", "serving", "installation", "version")
                                 if key in status[0]),
                "stop_drain": stopped[0], "http": sorted(endpoint)},
        "files": {
            "current": installations.CURRENT,
            "current_bytes": (root / installations.CURRENT).read_bytes().decode("ascii"),
            "record": f"{installations.FOLDER}/<version>.json",
            "record_keys": sorted(record),
            "token": registry.TOKEN,
            "releases": releases.FOLDER,
            "release_marker": releases.MARKER,
            "release_schema": releases.SCHEMA,
            "release_command": console.relative_to(folder).as_posix(),
            "switch_record": switch.RESULT,
            "switch_log": switch.LOG,
        },
    }


class UpdateHandshakeTest(unittest.TestCase):
    def test_the_handshake_between_releases_is_the_golden_one(self) -> None:
        golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
        found = surface()
        # A release's command is bin/cad, and Scripts/cad.exe on Windows: both are frozen.
        command = golden["files"].pop("release_command")
        found["files"]["release_command"] = {"posix": found["files"]["release_command"], "nt": command["nt"]} \
            if os.name != "nt" else {"posix": command["posix"], "nt": found["files"]["release_command"]}
        golden["files"]["release_command"] = command
        self.assertEqual(found, golden, "the update's handshake between releases changed: see this module's "
                                        "docstring before changing update_handshake.json")


def setUpModule() -> None:
    engine_daemon.isolate(unittest.addModuleCleanup)


if __name__ == "__main__":
    unittest.main()
