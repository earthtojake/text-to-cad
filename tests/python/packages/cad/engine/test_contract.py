"""The worker contract the library and the server both state (``cad.engine.contract``): an order names the
Python it comes from; a contract that is not the server's is refused in one line naming which side to
update and to what release; one contract of two releases builds, and the run then says once which side
to update."""

from __future__ import annotations

import io
import os
import re
import sys
import tomllib
import unittest
from pathlib import Path
from unittest import mock

from tests.python.support.paths import LIBRARY

from cad import model
from cad.engine import api, contract, places

OURS = {"protocol": 2, "format": "xbf/9", "kernel": "OCP 8.0"}


def named(release: str, protocol: int) -> dict:
    return {"executable": "/env/bin/python", "prefix": "/env", "release": release,
            "contract": {**OURS, "protocol": protocol}}


class ContractTest(unittest.TestCase):
    def test_the_contract_is_the_worker_protocol_the_document_format_and_the_pinned_kernel(self) -> None:
        from cad.engine.previous import FORMAT

        self.assertEqual(contract.CONTRACT, {"protocol": contract.PROTOCOL, "format": FORMAT,
                                             "kernel": f"OCP {contract.KERNEL}"})
        with (LIBRARY / "pyproject.toml").open("rb") as handle:
            pins = tomllib.load(handle)["project"]["optional-dependencies"]["build123d"]
        ocp = next(pin for pin in pins if pin.startswith("cadquery-ocp-novtk"))
        low, high = re.fullmatch(r"cadquery-ocp-novtk>=(\d+\.\d+),<(\d+\.\d+)", ocp).groups()
        self.assertEqual(contract.KERNEL, low, "the kernel the contract states is the one the library pins")
        self.assertEqual(high, f"{low.split('.')[0]}.{int(low.split('.')[1]) + 1}", "one minor release of OCP")

    def test_one_contract_is_never_refused_whatever_the_releases(self) -> None:
        for release in ("0.10.0", "0.10.2", "0.10.3"):
            self.assertIsNone(contract.refusal(named(release, 2), ours=OURS, server="0.10.2"))

    def test_an_older_cad_is_told_to_update_cad_here_to_the_server_s_release(self) -> None:
        self.assertEqual(contract.refusal(named("0.10.0", 1), ours=OURS, server="0.10.2"),
                         "cad here is 0.10.0, worker contract 1 (xbf/9, OCP 8.0); cad-server 0.10.2 speaks contract 2 "
                         "(xbf/9, OCP 8.0): update the cad package in this environment to 0.10.2")

    def test_a_newer_cad_is_told_to_update_cad_server_to_its_own_release(self) -> None:
        said = contract.refusal(named("0.10.3", 3), ours=OURS, server="0.10.2")
        self.assertEqual(said, "cad here is 0.10.3, worker contract 3 (xbf/9, OCP 8.0); cad-server 0.10.2 speaks "
                               "contract 2 (xbf/9, OCP 8.0): update cad-server to 0.10.3: run `cad update`")
        library = contract.refusal({}, ours=OURS, server="0.10.2")
        for line in (said, library):
            self.assertNotIn("\n", line)
            self.assertNotRegex(line, r"\b(pip|uv|uvx|install|text-to-cad)\b", "the packages named, no installer")
        self.assertNotIn("cad update", library, "the library's side names no command: `cad update` moves the server")

    def test_one_release_of_two_contracts_is_two_builds_of_it_which_no_update_mends(self) -> None:
        said = contract.refusal(named("0.10.2", 3), ours=OURS, server="0.10.2")
        self.assertEqual(said, "cad here is 0.10.2, worker contract 3 (xbf/9, OCP 8.0); cad-server 0.10.2 speaks "
                               "contract 2 (xbf/9, OCP 8.0): both are 0.10.2, but different builds of it: use one "
                               "build of both")

    def test_a_pre_release_or_development_build_is_ordered_and_named_with_no_update_that_cannot_reach_it(self) -> None:
        # PEP 440's order: a release's development builds, its pre-releases, the release, its post-releases.
        ordered = ["0.10.1.dev1", "0.10.1rc1.dev2", "0.10.1rc1", "0.10.1", "0.10.1.post1"]
        self.assertEqual(sorted(reversed(ordered), key=contract._order), ordered)
        self.assertTrue(contract.refusal(named("0.10.1rc1.dev2", 3), ours=OURS, server="0.10.0").endswith(
            ": update cad-server to 0.10.1rc1.dev2"), "newer, and `cad update` reaches no pre-release")
        self.assertTrue(contract.refusal(named("0.10.1rc1.dev2", 1), ours=OURS, server="0.10.1").endswith(
            ": update the cad package in this environment to 0.10.1"), "older than the release it leads to")
        self.assertEqual(contract.notice("0.10.0", "0.10.1rc1"), "cad here is 0.10.1rc1; cad-server is 0.10.0: "
                                                                "update cad-server to 0.10.1rc1")
        self.assertEqual(contract.notice("0.10.0", "0.10.1.post1"), "cad here is 0.10.1.post1; cad-server is 0.10.0: "
                                                                   "update cad-server to 0.10.1.post1: run `cad update`")

    def test_the_kernel_and_the_format_are_the_contract_too(self) -> None:
        for changed in ({"kernel": "OCP 8.1"}, {"format": "xbf/10"}):
            theirs = {**named("0.11.0", 2), "contract": {**OURS, **changed}}
            self.assertTrue(contract.refusal(theirs, ours=OURS, server="0.10.2").endswith(
                "update cad-server to 0.11.0: run `cad update`"))

    def test_an_order_from_a_base_the_server_made_names_no_python(self) -> None:
        here = contract.interpreter()
        self.assertEqual((here["release"], here["contract"]), (contract.release(), contract.CONTRACT))
        base = {"executable": "/base/bin/python", "prefix": "/base", "root": "/"}
        with mock.patch.object(places, "HOME", base):
            self.assertIsNone(contract.interpreter(), "cad run's script is built in the server's own environment")
        # An environment of a model's own packages (``cad run --with``, a script's header): its Python, and
        # the requirements ``cad run --with`` handed the program, which build its documents again.
        named = '{"with": ["pandas"], "script": "/w/check.py", "header": ["scipy"]}'
        with mock.patch.object(places, "HOME", base), mock.patch.object(places, "EXTRAS", ("pandas", "scipy")), \
                mock.patch.dict(os.environ, {places.RUN_WITH: named}):
            here = contract.interpreter()
        self.assertEqual((here["executable"], here["with"], here["header"]),
                         (sys.executable, ["pandas"], {"script": "/w/check.py", "with": ["scipy"]}))


@model
def plate():  # built by a stand-in engine below, never run here
    raise AssertionError("the engine is a stand-in")


class NoticeTest(unittest.TestCase):
    """The run of a script in its own Python says once, after its report, which side to update when the
    server that built it is another release of one contract."""

    def setUp(self) -> None:
        api._NOTICE.update(pid=None, line=None, said=False)
        self.orders: list[dict] = []

    def run_twice(self, here: str, server: str, home: dict | None = None) -> str:
        """``plate()`` called twice, built by a server of the release ``server`` for this library of
        ``here``: what the run said on stderr."""
        report = {"ok": True, "id": plate.id, "model": "plate", "source": {"script": str(plate.script), "name": "plate"}}

        def ask(order, *_args, **_kwargs):
            self.orders.append(order)
            return {"done": [report], "worker": {"pid": 1, "fresh": False}, "release": server}

        said = io.StringIO()
        with mock.patch.object(api, "_ask", ask), mock.patch.object(contract, "release", lambda: here), \
                mock.patch.object(places, "HOME", home), mock.patch("sys.stderr", said):
            plate()
            plate()
        return said.getvalue()

    def test_a_cad_older_than_the_server_says_to_update_it_here_once_a_run(self) -> None:
        self.assertEqual(self.run_twice("0.10.0", "0.10.2"),
                         "cad here is 0.10.0; cad-server is 0.10.2: update the cad package in this environment to 0.10.2 "
                         "for its fixes and features\n")
        self.assertEqual(self.orders[0]["interpreter"]["release"], "0.10.0", "the build names its Python and release")

    def test_a_cad_newer_than_the_server_says_to_update_cad_server(self) -> None:
        self.assertEqual(self.run_twice("0.10.3", "0.10.2"),
                         "cad here is 0.10.3; cad-server is 0.10.2: update cad-server to 0.10.3: run `cad update`\n")

    def test_one_release_says_nothing(self) -> None:
        self.assertEqual(self.run_twice("0.10.2", "0.10.2"), "")

    def test_cad_run_s_script_in_the_server_s_own_environment_says_nothing(self) -> None:
        base = {"executable": "/base/bin/python", "prefix": "/base", "root": "/"}
        self.assertEqual(self.run_twice("0.10.0", "0.10.2", home=base), "")
        self.assertNotIn("interpreter", self.orders[0])


if __name__ == "__main__":
    unittest.main()
