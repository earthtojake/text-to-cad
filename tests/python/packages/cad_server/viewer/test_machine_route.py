"""The viewer's ``/api/v1/machines``: a page watches a machine, waits on its readings and stops it
(the readers themselves are ``tests/python/packages/cad_server/test_machines.py``'s)."""

import json
import time
import unittest

from cad_server.machines import Reading
from cad_server.machines.watch import Watches

from .test_http_layer import ServerFixture


class ScriptedReader:
    """A reader that answers one reading forever."""

    def __init__(self, reading):
        self.reading = reading

    def open(self):
        pass

    def close(self):
        pass

    def read(self):
        return self.reading


class RouteTests(unittest.TestCase):
    def setUp(self):
        self.server = ServerFixture()
        self.addCleanup(self.server.close)
        self.reader = ScriptedReader(Reading(axes={"X": 7.0}, state="running", detail="Run"))
        self.server.app._machines = Watches(reader_for=lambda address: self.reader, period=0.01, retry=0.01)
        self.addCleanup(self.server.app._machines.close)
        self.headers = {"x-cad-viewer": "1", "content-type": "application/json"}

    def post(self, payload):
        status, _, body = self.server.request("POST", "/api/v1/machines", headers=self.headers, body=json.dumps(payload).encode())
        return status, json.loads(body or b"null")

    def test_watch_read_and_stop(self):
        status, state = self.post({"address": "grbl://fluidnc.local"})
        self.assertEqual((status, state["protocol"], state["address"]), (201, "grbl", "grbl://fluidnc.local:23"))
        deadline = time.monotonic() + 5
        while True:
            status, _, body = self.server.request("GET", f"/api/v1/machines/{state['id']}?after={state['version']}&wait=2")
            state = json.loads(body)
            if state["reading"] or time.monotonic() > deadline:
                break
        self.assertEqual((status, state["reading"]["axes"]), (200, {"X": 7.0}))
        self.assertEqual(self.server.request("DELETE", f"/api/v1/machines/{state['id']}", headers=self.headers)[0], 204)
        self.assertEqual(self.server.request("GET", f"/api/v1/machines/{state['id']}")[0], 404)

    def test_refusals(self):
        self.assertEqual(self.post({"address": "http://agent"})[0], 400)
        self.assertEqual(self.post({"addr": "grbl://x"})[0], 400)
        self.assertEqual(self.server.request("POST", "/api/v1/machines", body=b'{"address": "grbl://x"}')[0], 403,
                         "a page from another site cannot start one")
        _, state = self.post({"address": "grbl://x"})
        self.assertEqual(self.server.request("GET", f"/api/v1/machines/{state['id']}?after=x")[0], 400)
        self.assertEqual(self.server.request("PUT", "/api/v1/machines", headers=self.headers)[0], 405)


if __name__ == "__main__":
    unittest.main()
