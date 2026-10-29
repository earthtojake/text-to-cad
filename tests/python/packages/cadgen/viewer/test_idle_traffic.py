"""A page left open polls its server (`cadgen/viewer/engine_app.py`, `_idle`): what it asks for on its own
is no work, so a superseded engine can step aside under it; a document's data, a build, an export or an
action is work, served out first."""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cadgen/src")

from cadgen.viewer.engine_app import _idle  # noqa: E402


def request(method: str, path: str) -> SimpleNamespace:
    return SimpleNamespace(method=method, path=path)


class IdleTraffic(unittest.TestCase):
    def test_what_an_open_page_asks_for_on_its_own_is_idle(self) -> None:
        for path in ("/__cad/api/doc/480928dc/version?after=1&wait=25", "/__cad/server", "/__cad/catalog?file=%2Fa.step",
                     "/__cad/folder?path=%2F", "/__cad/search?q=a", "/__cad/version", "/__cad/language",
                     "/__cad/analytics", "/__cad/thumbnail?id=1", "/api/doc/480928dc/version"):
            with self.subTest(path=path):
                self.assertTrue(_idle(request("GET", path.split("?")[0])))
        self.assertTrue(_idle(request("POST", "/__cad/analytics/activity")))

    def test_a_documents_data_a_build_an_export_and_an_action_are_work(self) -> None:
        for method, path in (("GET", "/__cad/api/doc/480928dc"), ("GET", "/__cad/api/doc/480928dc/mesh"),
                             ("GET", "/__cad/xbf"), ("GET", "/__cad/asset"), ("GET", "/__cad/drawing"),
                             ("POST", "/__cad/update"), ("POST", "/__cad/pick"), ("POST", "/__cad/reveal"),
                             ("POST", "/__cad/analytics"), ("GET", "/__cad/server/anything"), ("GET", "/480928dc")):
            with self.subTest(method=method, path=path):
                self.assertFalse(_idle(request(method, path)))


if __name__ == "__main__":
    unittest.main()
