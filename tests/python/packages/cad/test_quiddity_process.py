#!/usr/bin/env python3

"""quiddity's own process (``cad.quiddity._process``, ``_recogniser``): each part handed over a pipe and answered
in turn, whatever the part before it did -- refused, failed, never finished (given up and the process stopped),
ended the process, held more memory than it may -- and the next part read by a new one; an import that fails
said once; a time for a part that is no positive, finite number refused by name; where quiddity is: this
environment, else the one the engine makes on first need, else the reason no environment holds it; an
environment that does not come in time, or cannot be made, not waited for and not asked for again until an
interval is over; and where quiddity publishes wheels, which the extra's marker and the registry say alike.

No kernel and no quiddity: the recogniser's process and its frames are the real ones, and what it imports as
quiddity is a stand-in (``tests/python/support/quiddity_stand_in.py``).
"""

from __future__ import annotations

import contextlib
import importlib.util
import sys
import threading
import time
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
        recogniser = _process.Recogniser()
        answered = []
        with recogniser as ask:
            for step in (b"ok 1", b"refuse", b"panic", b"hang", b"ok 2", b"die", b"ok 3", b""):
                # an answer is awaited as long as a part may take; the part that never answers is given up at once
                recogniser.timeout_s = 0.05 if step == b"hang" else _process.TIMEOUT_S
                answered.append(ask(step))
        good = {"document": {"schema_version": "stand-in"}, "anchors": [], "quiddity": "0.0.0"}
        self.assertEqual(answered[0], good)
        # quiddity's own refusal and its failure are answers: the process goes on.
        self.assertEqual(answered[1], {"reason": "refused", "detail": "no solid in the file", "quiddity": "0.0.0"})
        self.assertEqual(answered[2], {"reason": "failed", "detail": "RuntimeError: index out of bounds",
                                       "quiddity": "0.0.0"})
        # A part it never finishes is given up and the process stopped; the next part has a new one.
        self.assertEqual(answered[3], {"reason": "timed_out", "quiddity": "0.0.0",
                                       "detail": "quiddity did not finish the part in 0.05 s and was stopped"})
        self.assertEqual(answered[4], good)
        # A process that ends with a part says so, and how it ended.
        self.assertEqual((answered[5]["reason"], answered[5]["quiddity"]), ("stopped", "0.0.0"))
        self.assertRegex(answered[5]["detail"], r"^quiddity's process ended while it had the part \(exit 7\)")
        self.assertEqual(answered[6], good)
        self.assertEqual(answered[7], {"reason": "refused", "detail": "an empty STEP", "quiddity": "0.0.0"})

    def test_a_process_that_holds_more_memory_than_it_may_is_stopped_and_the_next_part_has_a_new_one(self) -> None:
        self.stand_in(STAND_IN)
        # the stand-in holds 256 MiB with the part and never answers; a recogniser's own process holds a tenth
        with mock.patch.object(_process, "RSS_MB", 128.0), mock.patch.object(_process, "WATCH_S", 0.02), \
                _process.Recogniser() as ask:
            answered = [ask(b"ok 1"), ask(b"hog"), ask(b"ok 2")]
        good = {"document": {"schema_version": "stand-in"}, "anchors": [], "quiddity": "0.0.0"}
        self.assertEqual(answered, [good, {"reason": "over_memory", "quiddity": "0.0.0",
                                           "detail": "quiddity's process held more than 128 MiB with the part and "
                                                     "was stopped"}, good])

    def test_a_time_for_a_part_that_is_no_positive_finite_number_is_refused_by_name(self) -> None:
        for given in (float("inf"), float("nan"), -1.0, 0, "3", True, None):
            with self.subTest(given=given), self.assertRaisesRegex(
                    ValueError, r"^timeout_s is a positive, finite number of seconds, not "):
                _process.Recogniser(timeout_s=given)
        self.assertEqual(_process.Recogniser(timeout_s=2).timeout_s, 2.0)

    def test_a_recogniser_ends_with_its_asker_in_the_middle_of_a_part_too(self) -> None:
        self.stand_in(STAND_IN)
        child = _process._Child(sys.executable, _process._child_env(repo_path("packages", "cad", "src")))
        self.addCleanup(child.end, kill=True)
        self.assertEqual(child.frame(_process.READY_S), {"quiddity": "0.0.0"})
        self.assertTrue(child.hand(b"hang"))
        # Its asker goes, with no word and no kill: the pipe closes, and the part it would never finish with it.
        child.process.stdin.close()
        self.assertEqual(child.process.wait(timeout=_process.READY_S), 0)
        self.assertIsNone(child.frame(_process.READY_S), "no answer, and its output's end")

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
        """An environment that holds no quiddity, in a process that has asked for none yet."""
        real = importlib.util.find_spec
        stack = contextlib.ExitStack()
        stack.enter_context(mock.patch("importlib.util.find_spec",
                                       lambda name, *rest: None if name == "quiddity" else real(name, *rest)))
        stack.enter_context(mock.patch.object(_process, "_REFUSED", None))
        return stack

    def test_an_environment_that_does_not_come_in_time_is_not_waited_for_nor_asked_for_again_at_once(self) -> None:
        asked: list[str] = []
        released = threading.Event()
        self.addCleanup(released.set)

        def never(_told: Any) -> None:
            asked.append("asked")
            released.wait()

        with self.without_quiddity(), mock.patch.object(_process, "published", return_value=True), \
                mock.patch.object(_process, "PROVIDE", never), mock.patch.object(_process, "ENVIRONMENT_S", 0.05):
            with _process.Recogniser() as ask:
                first = [ask(b"a part"), ask(b"another")]
            with _process.Recogniser() as ask:
                second = ask(b"a part")
            self.assertEqual((first[0]["reason"], first[0]["quiddity"]), ("not_installed", None))
            self.assertRegex(first[0]["detail"], r"^cad\[quiddity\]'s environment was not ready in 0\.05 s \(the engine "
                                                 r"goes on making it\): it is asked for again in 60 s")
            self.assertEqual((first[1], second), (first[0], first[0]))
            self.assertEqual(asked, ["asked"], "one wait, for every part and every call until the interval is over")
            # the interval over, it is asked for again
            until, failed = _process._REFUSED
            self.assertGreater(until, time.monotonic())
            _process._REFUSED = (time.monotonic() - 1.0, failed)
            with _process.Recogniser() as ask:
                ask(b"a part")
            self.assertEqual(asked, ["asked", "asked"])

    def test_a_making_that_fails_is_paid_for_once_until_the_interval_is_over(self) -> None:
        asked: list[str] = []

        def offline(_told: Any) -> str:
            asked.append("asked")
            raise _process.Unavailable("not_installed", "the engine could not make cad[quiddity]'s environment: uv "
                                                        "cannot reach the network")

        with self.without_quiddity(), mock.patch.object(_process, "published", return_value=True), \
                mock.patch.object(_process, "PROVIDE", offline):
            answers = []
            for _call in range(3):
                with _process.Recogniser() as ask:
                    answers.append(ask(b"a part"))
            self.assertEqual(answers, [{"reason": "not_installed", "quiddity": None,
                                        "detail": "the engine could not make cad[quiddity]'s environment: uv cannot "
                                                  "reach the network"}] * 3)
            self.assertEqual(asked, ["asked"])
            # an environment that comes is remembered as no failure
            _process._REFUSED = (time.monotonic() - 1.0, _process._REFUSED[1])
            with mock.patch.object(_process, "PROVIDE", lambda _told: sys.executable):
                self.assertEqual(_process._provided(), sys.executable)
            self.assertIsNone(_process._REFUSED)

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
