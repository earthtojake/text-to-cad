"""``cad <type> snapshot`` where the engine has no OpenGL context (``snapshot.NO_GL``) and this command carries no
kernel: the same snapshot is run by the installation's base from this process, so on its display (``xvfb-run cad
urdf snapshot ...``); with no display to lend, a kernel here, or any other failure, the engine's failure stands. The
engine's refusal is injected and the base's run recorded: nothing is drawn."""

from __future__ import annotations

import argparse
import io
import os
import unittest
from contextlib import redirect_stderr
from unittest import mock

from cad.engine import api, snapshot
from cad_server._internal import integration_env
from cad_server.engine import cli

ID = "0f8fad5b-d9cb-469f-a165-70867728950e"


def _args(document: str) -> argparse.Namespace:
    return argparse.Namespace(document=document, out="robot.png", display=None, camera="iso", grid=False, preview=False,
                              pose='{"elbow": 30}',
                              width=None, height=None, size_profile=None, annotation=None, measurements=None, json=False)


def _no_gl() -> Exception:
    return api._failed({"failed": "Unavailable: no X display for OpenGL", "type": snapshot.NO_GL})


class DrawnByTheBase(unittest.TestCase):
    def elsewhere(self, error: Exception, document: str, *, display: str | None = ":99", carries: bool = False,
                  platform: str = "linux") -> tuple[object, mock.Mock]:
        called = mock.Mock(return_value={"path": "robot.png", "width": 8, "height": 6, "report": {"ok": True}})
        environ = {"DISPLAY": display} if display else {}
        with mock.patch.dict(os.environ, environ, clear=False), \
                mock.patch("cad.engine.render.context.platform", return_value=platform), \
                mock.patch.object(integration_env, "carries", return_value=carries), \
                mock.patch.object(integration_env, "environment", return_value="/base/python"), \
                mock.patch.object(integration_env, "call", called), redirect_stderr(io.StringIO()):
            if not display:
                os.environ.pop("DISPLAY", None)
            return cli._drawn_elsewhere(error, _args(document), "cad urdf snapshot"), called

    def test_the_base_draws_a_file_and_a_held_document_on_this_display(self) -> None:
        found, called = self.elsewhere(_no_gl(), "robot.urdf")
        self.assertEqual(8, found["width"])
        python, document_type, operation, (source, out), options = called.call_args.args
        self.assertEqual(("/base/python", "urdf", "snapshot", "robot.png"), (python, document_type, operation, out))
        self.assertTrue(source.endswith("robot.urdf") and os.path.isabs(source))
        self.assertEqual({"camera": "iso", "pose": '{"elbow": 30}'}, options)
        _found, called = self.elsewhere(_no_gl(), ID)
        self.assertEqual(("model", [ID, "robot.png"]), called.call_args.args[1:4:2])

    def test_the_engine_s_failure_stands_otherwise(self) -> None:
        for name, error, options in (("another failure", api.EngineError("MemoryError"), {}),
                                     ("no display to lend", _no_gl(), {"display": None}),
                                     ("a kernel here", _no_gl(), {"carries": True})):
            with self.subTest(name):
                found, called = self.elsewhere(error, "robot.urdf", **options)
                self.assertIsNone(found)
                called.assert_not_called()
        found, _called = self.elsewhere(_no_gl(), "robot.urdf", display=None, platform="darwin")
        self.assertIsNotNone(found, "macOS and Windows lend the session's display")


if __name__ == "__main__":
    unittest.main()
