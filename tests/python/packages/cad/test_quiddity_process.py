#!/usr/bin/env python3

"""quiddity's own process (``cad.quiddity._process``, ``_recogniser``): each part handed over a pipe and answered
in turn, whatever the part before it did -- refused, failed, never finished (given up and the process stopped),
ended the process -- and the next part read by a new one; an import that fails said once; where quiddity is: this
environment, else the one the engine makes on first need, else the reason no environment holds it; and where
quiddity publishes wheels, which the extra's marker and the registry say alike.

No kernel and no quiddity: the recogniser's process and its frames are the real ones, and what it imports as
quiddity is a stand-in (``tests/python/support/quiddity_stand_in.py``).
"""

from __future__ import annotations

import importlib.util
import tomllib
import unittest
from typing import Any
from unittest import mock

from cad import registry
from cad.quiddity import _process

from tests.python.support.paths import repo_path
from tests.python.support.quiddity_stand_in import STAND_IN, UNIMPORTABLE, StandIn


class ProcessTest(StandIn):
    def test_each_part_is_answered_whatever_the_one_before_it_did(self) -> None:
        self.stand_in(STAND_IN)
        with _process.Recogniser(timeout_s=0.5) as ask:
            answered = [ask(step) for step in (b"ok 1", b"refuse", b"panic", b"hang", b"ok 2", b"die", b"ok 3", b"")]
        good = {"document": {"schema_version": "stand-in"}, "anchors": [], "quiddity": "0.0.0"}
        self.assertEqual(answered[0], good)
        # quiddity's own refusal and its failure are answers: the process goes on.
        self.assertEqual(answered[1], {"reason": "refused", "detail": "no solid in the file", "quiddity": "0.0.0"})
        self.assertEqual(answered[2], {"reason": "failed", "detail": "RuntimeError: index out of bounds",
                                       "quiddity": "0.0.0"})
        # A part it never finishes is given up and the process stopped; the next part has a new one.
        self.assertEqual(answered[3], {"reason": "timed_out", "quiddity": "0.0.0",
                                       "detail": "quiddity did not finish the part in 0.5 s and was stopped"})
        self.assertEqual(answered[4], good)
        # A process that ends with a part says so, and how it ended.
        self.assertEqual((answered[5]["reason"], answered[5]["quiddity"]), ("stopped", "0.0.0"))
        self.assertRegex(answered[5]["detail"], r"^quiddity's process ended while it had the part \(exit 7\)")
        self.assertEqual(answered[6], good)
        self.assertEqual(answered[7], {"reason": "refused", "detail": "an empty STEP", "quiddity": "0.0.0"})

    def test_an_import_that_fails_is_said_once_and_no_process_is_started_again(self) -> None:
        self.stand_in(UNIMPORTABLE)
        started: list[Any] = []
        child = _process._Child

        def counted(*given: Any) -> Any:
            started.append(given)
            return child(*given)

        with mock.patch.object(_process, "_Child", counted), _process.Recogniser() as ask:
            answered = [ask(b"ok 1"), ask(b"ok 2")]
        self.assertEqual(len(started), 1)
        self.assertEqual(answered[0], answered[1])
        self.assertEqual((answered[0]["reason"], answered[0]["quiddity"]), ("not_installed", None))
        self.assertRegex(answered[0]["detail"], r" does not import quiddity: ImportError: no wheel was built for this "
                                                r"machine$")


class WhereQuiddityIsTest(unittest.TestCase):
    def without_quiddity(self) -> Any:
        real = importlib.util.find_spec
        return mock.patch("importlib.util.find_spec", lambda name, *rest: None if name == "quiddity" else real(name, *rest))

    def test_where_no_environment_holds_quiddity_the_result_says_why(self) -> None:
        prefix = r"^quiddity comes with cad's quiddity integration, cad\[quiddity\], "
        cases = [
            ("no_wheel", False, lambda _told: self.fail("no environment is made where no wheel exists"),
             prefix + r"which installs it only where quiddity publishes wheels, macOS, Linux x86_64 and aarch64 "
                      r"\(glibc 2\.28 or newer\) and Windows x86_64, and this is "),
            ("not_installed", True, lambda _told: None,
             prefix + r"which this environment does not hold, and no engine answered to make its environment: "
                      r"run the script with cad run"),
        ]
        for reason, wheel, provide, said in cases:
            with self.subTest(reason), self.without_quiddity(), mock.patch.object(_process, "published", return_value=wheel), \
                    mock.patch.object(_process, "PROVIDE", provide), _process.Recogniser() as ask:
                answer = ask(b"a part")
                self.assertEqual((answer["reason"], answer["quiddity"]), (reason, None))
                self.assertRegex(answer["detail"], said)

        def offline(_told: Any) -> str:
            raise _process.Unavailable("not_installed", "the engine could not make cad[quiddity]'s environment: uv "
                                                        "cannot reach the network")

        with self.without_quiddity(), mock.patch.object(_process, "published", return_value=True), \
                mock.patch.object(_process, "PROVIDE", offline), _process.Recogniser() as ask:
            self.assertEqual(ask(b"a part"), {"reason": "not_installed", "quiddity": None,
                                             "detail": "the engine could not make cad[quiddity]'s environment: uv "
                                                       "cannot reach the network"})

    def test_the_engine_is_asked_over_its_door_and_an_engine_without_the_request_is_none(self) -> None:
        told: list[str] = []

        def answering(answer: Any) -> Any:
            def request(message: dict[str, Any], on_log: Any = None, **_given: Any) -> Any:
                self.assertEqual(message, {"op": "integration", "integration": "quiddity"})
                on_log({"log": "making the quiddity integration's environment, once"})
                return answer
            return mock.patch("cad.engine.client.request", request)

        with answering({"ok": True, "python": "/env/bin/python"}):
            self.assertEqual(_process._engine(told.append), "/env/bin/python")
        self.assertEqual(told, ["making the quiddity integration's environment, once"])
        for answer in (None, {"failed": "unknown request 'integration'"},
                       {"failed": "no integration 'quiddity': one of build123d, coacd"}):
            with answering(answer):
                self.assertIsNone(_process._engine(told.append))
        with answering({"failed": "uv cannot reach the network"}):
            with self.assertRaisesRegex(_process.Unavailable, r"could not make cad\[quiddity\]'s environment: uv cannot"):
                _process._engine(told.append)

    def test_quiddity_publishes_wheels_where_the_extra_and_the_registry_say(self) -> None:
        for system, machine, glibc, wheel in [
                ("Darwin", "arm64", None, True), ("Darwin", "x86_64", None, True),
                ("Windows", "AMD64", None, True), ("Windows", "ARM64", None, False),
                ("Linux", "x86_64", (2, 28), True), ("Linux", "aarch64", (2, 39), True),
                ("Linux", "x86_64", (2, 17), False), ("Linux", "x86_64", None, False),
                ("Linux", "armv7l", (2, 39), False), ("FreeBSD", "amd64", None, False)]:
            with self.subTest(system=system, machine=machine, glibc=glibc):
                self.assertIs(_process.published(system, machine, glibc), wheel)
        # The registry's platforms are the extra's marker: it installs nothing on Windows on ARM.
        entry = registry.INTEGRATIONS["quiddity"]
        self.assertEqual((entry.extra, entry.process, entry.python), ("quiddity", "separate", None))
        self.assertEqual(entry.platforms, ("macOS arm64", "macOS x86-64", "Linux x86-64", "Linux arm64", "Windows x86-64"))
        extras = tomllib.loads(repo_path("packages", "cad", "pyproject.toml").read_text(encoding="utf-8"))
        (requirement,) = extras["project"]["optional-dependencies"]["quiddity"]
        name, _, marker = requirement.partition(";")
        self.assertEqual(name.strip(), "quiddity==0.5.5")
        self.assertEqual(marker.strip(), "sys_platform == 'darwin' or (sys_platform == 'linux' and (platform_machine == "
                                         "'x86_64' or platform_machine == 'aarch64')) or (sys_platform == 'win32' and "
                                         "platform_machine == 'AMD64')")


if __name__ == "__main__":
    unittest.main()
