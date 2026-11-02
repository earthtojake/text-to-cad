"""The daemon's supervisor, by its services' declarations: what a declaration says decides how its
processes are leased, counted, shed and drained; and the protocol every process speaks, with a
small real child. The workers' own rules through the daemon are test_pool's."""

from __future__ import annotations

import dataclasses
import io
import itertools
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from tests.python.support.paths import add_sources

add_sources()  # the three packages' sources, as PYTHONPATH names them

from cad_server.engine import supervisor as supervised  # noqa: E402
from cad_server.engine.supervisor import Gone, Process, Service, Standby, Supervisor, Words  # noqa: E402

_PIDS = itertools.count(1)
WORDS = Words("the {label} did not start", "the {name} exited ({code})", "{error}")
# Today's two kinds, as far as scheduling is concerned: a counted, watched, drained one with a standby,
# and one that does not count.
WORKERS = Service("worker", ("{python}",), "kernel", "lease", WORDS, binding=("PYTHONPATH",), rank=2,
                  watched_rank=3, noted=("script", "builds"), drain=True,
                  standby=Standby(("--standby",), "adopt", notice="the kernel loads", patience=0.01))
RENDERS = Service("render", ("{python}",), "kernel", "daemon", WORDS, key="id", counted=False, rank=1)


def await_(condition, what: str, seconds: float = 30.0) -> None:
    deadline = time.monotonic() + seconds
    while not condition():
        if time.monotonic() > deadline:
            raise AssertionError(f"timed out waiting for {what}")
        time.sleep(0.01)


class Fake:
    """A process as the supervisor sees one, its life recorded in ``said``."""

    def __init__(self, said: list, service: Service, key: str, label: str, environment: dict, cwd: str | None,
                 standby: bool, rss: float | None = 100.0) -> None:
        self.said, self.service, self.key, self.label, self.environment = said, service, key, label, environment
        self.cwd, self.standby = cwd, standby
        self.pid, self.requests, self.rss, self.started = next(_PIDS), 0, rss, time.time()
        self.leased, self.since, self.used, self.retired, self.stopped = False, 0.0, time.monotonic(), False, False
        said.append(("launch", label))

    def alive(self) -> bool:
        return not self.stopped

    def stop(self) -> None:
        self.said.append(("stop", self.label))
        self.stopped = True

    def adopt(self, key: str, label: str, environment: dict, cwd: str | None) -> None:
        self.key, self.label, self.environment, self.cwd = key, label, environment, cwd


class SchedulingTest(unittest.TestCase):
    def supervisor(self, cap: int, services=(WORKERS, RENDERS), memory: float | None = None,
                   watched: set | None = None, gate: threading.Event | None = None) -> Supervisor:
        self.said: list = []
        watched = set() if watched is None else watched

        def launch(service, key, label, environment, cwd, standby):
            if standby and gate is not None:
                gate.wait(30)
            return Fake(self.said, service, key, label, environment, cwd, standby)

        def drain(process) -> None:
            self.said.append(("drain", process.label, process.alive(),
                              any(held is process for held in made.table.values())))

        made = Supervisor(cap, services, launch=launch, memory=lambda: memory, drain=drain,
                          watched=lambda process: process.label in watched)
        self.addCleanup(made.stop)
        return made

    def used(self, supervisor: Supervisor, service: str, *keys: str) -> list:
        """A process each, leased and let go in turn: the first least recently used."""
        found = []
        for key in keys:
            process = supervisor.lease(service, key, {})
            supervisor.release(process)
            found.append(process)
        return found

    def standing(self, supervisor: Supervisor) -> Fake:
        supervisor.enable_standby("worker")
        supervisor.stand("worker", {})
        await_(lambda: supervisor.standby("worker") is not None, "the standby")
        return supervisor.standby("worker")

    def test_a_service_that_does_not_count_is_never_held_by_the_cap_nor_costs_a_counted_process(self) -> None:
        supervisor = self.supervisor(1)
        busy = supervisor.lease("worker", "a.py", {})
        got: list = []
        waiting = threading.Thread(target=lambda: got.append(supervisor.lease("worker", "b.py", {})), daemon=True)
        waiting.start()
        await_(lambda: supervisor.waiting("worker") == 1, "b to wait for a slot")
        drawing = supervisor.lease("render", "doc", {}, label="/w/part.xbf")  # behind no one, past the cap
        self.assertEqual((drawing.label, supervisor.waiting("render"), busy.stopped), ("/w/part.xbf", 0, False))
        supervisor.release(drawing)
        supervisor.release(busy)
        waiting.join(5)
        self.assertTrue(busy.stopped and not drawing.stopped, "the cap's victim is the counted one, never the render")
        self.assertEqual([process.label for process in supervisor.processes("worker")], ["b.py"])
        self.assertEqual([row["reason"] for row in supervisor.retired], ["LRU"])

    def test_a_standby_being_started_holds_its_slot_and_then_makes_room(self) -> None:
        gate = threading.Event()
        supervisor = self.supervisor(1, gate=gate)
        supervisor.enable_standby("worker")
        supervisor.stand("worker", {})
        got: list = []
        other = threading.Thread(target=lambda: got.append(supervisor.lease("worker", "a.py", {"PYTHONPATH": "/x"})),
                                 daemon=True)
        other.start()
        await_(lambda: supervisor.waiting("worker") == 1, "a lease of another binding to wait: the slot is held")
        gate.set()
        other.join(5)
        self.assertEqual(got[0].label, "a.py")
        self.assertEqual([said for said in self.said if said[1] == "standby"], [("launch", "standby"), ("stop", "standby")])
        self.assertEqual(list(supervisor.retired), [], "a standby that makes room is no retirement")

    def shed_in_order(self, services) -> list[str]:
        """A standby, two render processes, two workers no page watches and one a page watches, each
        of 100 MB, under a cap of 250 MB: what goes, in order."""
        supervisor = self.supervisor(8, services, memory=250.0, watched={"watched.py"})
        supervisor.memory = lambda: None  # held off while they are made
        self.used(supervisor, "worker", "watched.py")
        self.used(supervisor, "render", "old-doc", "new-doc")
        self.used(supervisor, "worker", "old.py", "new.py")
        self.standing(supervisor)
        supervisor.memory = lambda: 250.0
        return [process.label for process in supervisor.shed()]

    def test_memory_is_shed_by_declared_rank_and_least_recently_used_within_one(self) -> None:
        from cad_server.engine.services import RENDER, WORKER

        self.assertEqual(self.shed_in_order((WORKER, RENDER)), ["standby", "old-doc", "new-doc", "old.py"],
                         "the daemon's: the standby, render processes, then workers no page watches")
        swapped = (dataclasses.replace(WORKER, rank=1), dataclasses.replace(RENDER, rank=2))
        self.assertEqual(self.shed_in_order(swapped), ["standby", "old.py", "new.py", "old-doc"],
                         "the order is the declarations'")

    def test_shedding_skips_the_busy_and_the_unmeasured_and_pressure_takes_the_standby_at_once(self) -> None:
        supervisor = self.supervisor(8, memory=None)
        unmeasured, measured, busy = self.used(supervisor, "worker", "unmeasured.py", "measured.py", "busy.py")
        unmeasured.rss = None
        busy = supervisor.lease("worker", "busy.py", {})
        spare = self.standing(supervisor)
        self.assertEqual(supervisor.shed(pressure=True), [spare], "no cap: under pressure the standby alone goes")
        supervisor.memory = lambda: 150.0
        self.assertEqual(supervisor.shed(), [measured], "the unmeasured one frees nothing countable; the busy one stays")
        self.assertFalse(busy.stopped or unmeasured.stopped)
        self.assertEqual([row["reason"] for row in supervisor.retired], ["RSS", "pressure"])

    def test_a_count_cap_victim_is_the_lowest_ranked_idle_process(self) -> None:
        kept = Service("kept", ("{python}",), "kernel", "lease", WORDS, rank=4, noted=("script", "builds"))
        supervisor = self.supervisor(2, (WORKERS, kept))
        older, = self.used(supervisor, "kept", "kept.py")
        newer, = self.used(supervisor, "worker", "worker.py")
        supervisor.lease("worker", "third.py", {})
        self.assertTrue(newer.stopped and not older.stopped, "rank first, then least recently used")

    def test_a_victim_is_drained_alive_and_out_of_the_table_then_stopped_before_the_next_starts(self) -> None:
        supervisor = self.supervisor(1)
        self.used(supervisor, "worker", "old.py")
        self.said.clear()
        supervisor.lease("worker", "new.py", {})
        self.assertEqual(self.said, [("drain", "old.py", True, False), ("stop", "old.py"), ("launch", "new.py")])

    def test_a_drain_that_fails_still_stops_and_the_daemon_s_stop_drains_nothing(self) -> None:
        supervisor = self.supervisor(1)
        process = supervisor.lease("worker", "a.py", {})
        process.retired = True  # over its memory cap after its request
        supervisor.drain = mock.Mock(side_effect=RuntimeError("the documents could not be taken"))
        supervisor.release(process)
        self.assertTrue(process.stopped)
        self.assertEqual(supervisor.retired[0]["reason"], "RSS")
        survivor = supervisor.lease("worker", "b.py", {})
        supervisor.release(survivor)
        supervisor.drain.reset_mock()
        supervisor.stop()
        self.assertTrue(survivor.stopped)
        supervisor.drain.assert_not_called()

    def test_a_process_that_dies_idle_leaves_at_the_next_grant_noted_as_its_service_says(self) -> None:
        supervisor = self.supervisor(1)
        worker, = self.used(supervisor, "worker", "a.py")
        drawing, = self.used(supervisor, "render", "doc")
        worker.stopped = drawing.stopped = True  # each died idle
        supervisor.lease("worker", "b.py", {})  # the next grant: its slot was free
        self.assertEqual((supervisor.processes("worker")[0].label, supervisor.processes("render")),
                         ("b.py", []))
        self.assertEqual([(row["script"], row["reason"]) for row in supervisor.retired], [("a.py", "exited")],
                         "a service that notes nothing is not noted")

    def test_a_declaration_is_refused_by_what_it_does_not_offer(self) -> None:
        for change, said in ((dict(env="parent"), "env is 'parent'"), (dict(environment="python3"), "absolute path"),
                             (dict(concurrency=2), "concurrency is 2"), (dict(stderr="drop"), "stderr is 'drop'"),
                             (dict(interpreter="caller"), "interpreter is 'caller'")):
            with self.subTest(change=change), self.assertRaisesRegex(ValueError, said):
                dataclasses.replace(WORKERS, **change)

    def caller_s(self, cap: int) -> tuple[Supervisor, list]:
        """A supervisor whose workers a lease may start in its caller's Python, and what it launched."""
        supervisor = self.supervisor(cap, (dataclasses.replace(WORKERS, interpreter="lease"), RENDERS))
        started: list = []

        def launch(service, key, label, environment, cwd, standby, python=None):
            started.append((label, python))
            return Fake(self.said, service, key, label, environment, cwd, standby)

        supervisor.launch = launch
        return supervisor, started

    def test_a_key_leased_in_its_caller_s_environment_is_a_process_of_its_own_and_never_the_standby(self) -> None:
        supervisor, started = self.caller_s(4)
        spare = self.standing(supervisor)
        base = supervisor.lease("worker", "a.py", {})
        self.assertIs(base, spare, "the server's own Python: the standby, taken")
        await_(lambda: supervisor.standby("worker") is not None, "another standby")
        theirs = supervisor.lease("worker", "a.py", {}, python="/venv/bin/python", python_key="/venv 0.10.0")
        self.assertIsNot(theirs, base)
        self.assertIsNotNone(supervisor.standby("worker"), "a lease in its caller's Python takes no standby")
        other = supervisor.lease("worker", "a.py", {}, python="/other/bin/python", python_key="/other 0.10.0")
        for process in (base, theirs, other):
            supervisor.release(process)
        self.assertEqual(started[-2:], [("a.py", "/venv/bin/python"), ("a.py", "/other/bin/python")])
        # One environment's, whatever spelling of its Python asks: the process its first lease started.
        self.assertIs(supervisor.lease("worker", "a.py", {}, python="/venv/bin/python3", python_key="/venv 0.10.0"),
                      theirs)
        self.assertEqual(len(started), 4, "no process started for another spelling of one environment's Python")
        self.assertIs(supervisor.live("worker", "a.py", "/other 0.10.0"), other)
        self.assertIs(supervisor.live("worker", "a.py"), base)
        self.assertFalse(any(process.stopped for process in (base, theirs, other)))
        self.assertEqual(list(supervisor.retired), [], "no environment replaced another's process")
        with self.assertRaisesRegex(ValueError, "a render runs its own environment's Python"):
            supervisor.lease("render", "doc", {}, python="/venv/bin/python")

    def test_a_lease_in_its_caller_s_python_makes_room_at_the_cap_with_an_idle_worker_before_the_standby(self) -> None:
        supervisor, started = self.caller_s(2)
        spare = self.standing(supervisor)
        idle, = self.used(supervisor, "worker", "a.py")  # the standby, taken
        await_(lambda: supervisor.standby("worker") is not None, "another standby: the cap is full")
        standby = supervisor.standby("worker")
        self.assertIs(idle, spare)
        theirs = supervisor.lease("worker", "b.py", {}, python="/venv/bin/python", python_key="/venv 0.10.0")
        self.assertTrue(idle.stopped, "the idle worker made room")
        self.assertIs(supervisor.standby("worker"), standby, "the standby stays for the server's own builds")
        self.assertFalse(standby.stopped)
        self.assertEqual([row["reason"] for row in supervisor.retired], ["LRU"])
        supervisor.release(theirs)

    def test_waiting_at_the_cap_a_lease_in_its_caller_s_python_holds_up_no_build_in_the_server_s_own(self) -> None:
        supervisor, _started = self.caller_s(2)
        busy = supervisor.lease("worker", "a.py", {})
        self.standing(supervisor)
        standby = supervisor.standby("worker")
        got: list = []
        theirs = threading.Thread(target=lambda: got.append(supervisor.lease(
            "worker", "b.py", {}, python="/venv/bin/python", python_key="/venv 0.10.0")), daemon=True)
        theirs.start()
        await_(lambda: supervisor.waiting("worker") == 1, "the caller's lease to wait for the busy worker")
        self.assertFalse(standby.stopped, "a busy worker will be free: the standby stays")
        # A build in the server's own Python behind it takes the standby the waiting one cannot.
        self.assertIs(supervisor.lease("worker", "c.py", {}), standby)
        supervisor.release(busy)
        theirs.join(5)
        self.assertTrue(got and busy.stopped, "the caller's lease took the slot of the worker once it was free")

    def test_at_a_cap_of_one_a_lease_in_its_caller_s_python_takes_the_standby_s_slot_and_it_stands_again(self) -> None:
        # The standby is all that holds the cap: the slot is the lease's, never a wait on nothing.
        supervisor, started = self.caller_s(1)
        spare = self.standing(supervisor)
        theirs = supervisor.lease("worker", "b.py", {}, python="/venv/bin/python", python_key="/venv 0.10.0")
        self.assertTrue(spare.stopped, "the standby retired for its slot")
        self.assertEqual((started[-1], list(supervisor.retired)), (("b.py", "/venv/bin/python"), []), "unnoted")
        # A build in the server's own Python behind it waits for that worker to be free, then takes its slot.
        got: list = []
        behind = threading.Thread(target=lambda: got.append(supervisor.lease("worker", "a.py", {})), daemon=True)
        behind.start()
        await_(lambda: supervisor.waiting("worker") == 1, "the build behind it to wait for the slot")
        supervisor.release(theirs)
        behind.join(5)
        self.assertTrue(got and theirs.stopped, "the idle worker made room")
        self.assertIsNone(supervisor.standby("worker"), "no room for the standby while a worker holds the slot")
        # The slot free again (the worker over its memory cap): the standby owed stands again.
        got[0].retired = True
        supervisor.release(got[0])
        await_(lambda: supervisor.standby("worker") is not None, "the standby owed, standing again")

    def test_a_build_s_worker_is_its_environment_s_and_its_release_s_whatever_spelling_names_its_python(self) -> None:
        from cad.engine import contract
        from cad_server.engine.daemon import Daemon

        engine = Daemon(cap=1)
        self.addCleanup(engine.shutdown)
        folder = Path(tempfile.mkdtemp(prefix="caller-venv-")).resolve()
        self.addCleanup(shutil.rmtree, folder, True)
        venv, alias = folder / "venv", folder / "alias"
        (venv / "bin").mkdir(parents=True)
        if os.name != "nt":
            alias.symlink_to(venv, target_is_directory=True)

        def order(executable: str, prefix: Path, release: str) -> dict:
            return {"interpreter": {"executable": executable, "prefix": str(prefix), "release": release,
                                    "contract": dict(contract.CONTRACT)}}

        python, key = engine.caller(order(str(venv / "bin" / "python"), venv, "0.10.0"))
        self.assertEqual(python, str(venv / "bin" / "python"), "the Python it runs: the one this build names")
        spelled = [engine.caller(order(str(venv / "bin" / name), venv, "0.10.0"))[1] for name in ("python3", "python3.14")]
        self.assertEqual(spelled, [key, key], "one environment, one key, whatever spelling of its Python")
        if os.name != "nt":
            self.assertEqual(engine.caller(order(str(alias / "bin" / "python"), alias, "0.10.0"))[1], key,
                             "its folder as the system resolves it")
        self.assertNotEqual(engine.caller(order(str(venv / "bin" / "python"), venv, "0.10.1"))[1], key,
                            "another release of cad there, under one contract: a worker of its own")
        self.assertEqual(engine.caller({}), (None, None), "an order that names no Python: the server's own")

    def test_a_held_document_whose_own_python_s_worker_is_gone_is_not_held_and_asked_of_no_other(self) -> None:
        from cad_server.engine.daemon import Daemon

        engine = Daemon(cap=2)
        self.addCleanup(engine.shutdown)
        asked: list = []

        class Worker(Fake):
            def request(self, message, sink=None, payload=b""):
                asked.append(message)
                return {"done": {"files": []}}

        engine.supervisor.launch = lambda service, key, label, environment, cwd, standby, **kw: Worker(
            [], service, key, label, environment, cwd, standby)
        base = engine.lease("/w/a.py", {})  # the script's worker in the server's own Python
        engine.release(base)
        ident = "6f1c2a4e-1b2c-5d3e-8f4a-0123456789ab"
        sent: list = []
        engine.handle({"op": "export", "destinations": ["/w/a.step"], "source": {
            "script": "/w/a.py", "function": "a", "held": ident, "via": "/w/a.py",
            "python_key": "/venv\x000.10.0"}}, sent.append)
        self.assertEqual(asked, [], "never asked of the server's own worker of its script")
        self.assertEqual(sent[0]["state"], "unsaved")
        self.assertIn(ident, sent[0]["failed"])


# The child a protocol test starts: the frames as a service's process sends them, by request.
CHILD = r"""
import json, os, queue, sys, threading, time

mode = sys.argv[1] if len(sys.argv) > 1 else ""
out = os.fdopen(os.dup(1), "wb")
os.dup2(2, 1)
lock = threading.Lock()


def send(message, payload=b""):
    if payload:
        message = dict(message, bytes=len(payload))
    with lock:
        out.write(json.dumps(message).encode() + b"\n" + payload)
        out.flush()


if mode == "silent":  # never says it is ready; leaves a file named by its process in the folder given
    open(os.path.join(sys.argv[2], str(os.getpid())), "w").close()
    while True:
        time.sleep(1)
out.write(b"a banner, no frame\n")
send({"ready": os.getpid(), "rssMb": 7})
if mode == "deaf":  # never reads its stdin, so its end is no reason to go
    while True:
        time.sleep(1)
asked, requests, stdin = threading.Event(), queue.Queue(), sys.stdin.buffer


def read():
    for line in stdin:
        request = json.loads(line)
        payload = stdin.read(request["bytes"]) if request.get("bytes") else b""
        if str(request.get("id", "")).startswith("?"):
            send({"id": request["id"], "answer": request["op"]})
            asked.set()
        else:
            requests.put((request, payload))
    requests.put(None)


threading.Thread(target=read, daemon=True).start()
while (found := requests.get()) is not None:
    request, payload = found
    op = request["op"]
    if op == "chatty":
        send({"log": "a line"})
        send({"notice": "a notice"})
        send({"progress": {"stage": "one"}})
        send({"saved": {"ident": "d"}}, b"saved\nbytes")
        send({"progress": {"stage": "two"}})
        send({"done": op, "rssMb": 9})
    elif op == "echo":
        send({"done": op}, payload)
    elif op == "slow":
        asked.wait(30)
        send({"done": op})
    elif op == "retire":
        send({"done": op, "retire": True})
    elif op == "cap":
        send({"done": request.get("rssCapMb", "none given")})
    elif op == "die":
        sys.stderr.write("dying words\n")
        sys.stderr.flush()
        os._exit(3)
"""


class ProtocolTest(unittest.TestCase):
    """A process as the supervisor starts one, speaking to a real child of a sibling environment."""

    def service(self, *mode: str, **changes) -> Service:
        return Service("child", ("{python}", "-c", CHILD, *mode), sys.executable, "daemon",
                       Words("the child {label} did not start", "the child {name} exited ({code}) mid-request",
                             "the child {name} is gone ({error})"), bytecode="read-only", cwd="inherit", key="id",
                       events=("saved",), noted=("document", "requests"), **changes)

    def start(self, service: Service, **hooks) -> Process:
        process = Process.start(service, "doc", "/w/doc.xbf", {}, **hooks)
        self.addCleanup(process.kill)
        return process

    def test_frames_reach_whoever_asked_in_order_and_events_reach_their_hook(self) -> None:
        heard, events, followed = [], [], []
        process = self.start(self.service(), on_progress=lambda _process, frame: heard.append(frame),
                             on_event={"saved": lambda _process, frame, payload: events.append((frame, payload))})
        self.assertGreater(process.pid, 0)
        self.assertEqual(process.rss, 7, "its ready frame, after a line that is no frame")
        process.followers.append(followed.append)
        sent: list = []
        answer = process.request({"op": "chatty"}, sent.append)
        self.assertEqual(answer, {"done": "chatty"})
        self.assertEqual(sent, [{"log": "a line"}, {"log": "a notice", "stream": "notice"},
                                {"progress": {"stage": "one"}}, {"progress": {"stage": "two"}}])
        self.assertEqual((heard, process.progress, process.rss), ([{"stage": "one"}, {"stage": "two"}],
                                                                    {"stage": "two"}, 9))
        self.assertEqual(followed, [{"progress": {"stage": "one"}}, {"progress": {"stage": "two"}}])
        self.assertEqual(events, [({"ident": "d"}, b"saved\nbytes")], "an event never answers a request")
        payload = b"\n{\"not\": \"a frame\"}\n" * 3
        self.assertEqual(process.request({"op": "echo"}, None, payload)["payload"], payload)
        self.assertEqual(process.requests, 2)

    def test_a_question_is_answered_while_a_request_runs(self) -> None:
        process = self.start(self.service())
        answers: list = []
        slow = threading.Thread(target=lambda: answers.append(process.request({"op": "slow"})), daemon=True)
        slow.start()
        await_(lambda: process.op == "slow", "the slow request to run")
        self.assertEqual(process.question({"op": "where"}, timeout=30)["answer"], "where")
        slow.join(30)
        self.assertEqual(answers, [{"done": "slow"}], "the request then answered, nothing crossed")

    def test_a_child_gone_mid_request_is_said_with_its_stderr_and_the_next_lease_starts_another(self) -> None:
        service = self.service(stderr="relay")
        supervisor = Supervisor(1, (service,))
        self.addCleanup(supervisor.stop)
        process = supervisor.lease("child", "doc", {}, label="/w/doc.xbf")
        with self.assertRaises(Gone) as caught:
            process.request({"op": "die"})
        self.assertEqual((caught.exception.during, caught.exception.code), (True, 3))
        self.assertIn("the child doc.xbf exited (3) mid-request", str(caught.exception))
        self.assertIn("dying words", str(caught.exception))
        supervisor.release(process)
        self.assertEqual(supervisor.retired[0]["reason"], "exited")
        again = supervisor.lease("child", "doc", {}, label="/w/doc.xbf")
        self.assertNotEqual(again.pid, process.pid)
        self.assertEqual(again.request({"op": "echo"}), {"done": "echo"})
        supervisor.release(again)

    def test_each_request_carries_the_supervisor_s_memory_cap(self) -> None:
        cap = [1234.0]
        supervisor = Supervisor(1, (self.service(),), memory=lambda: cap[0])
        self.addCleanup(supervisor.stop)
        process = supervisor.lease("child", "doc", {})
        self.assertEqual(process.request({"op": "cap"}), {"done": 1234.0})
        cap[0] = None
        self.assertEqual(process.request({"op": "cap"}), {"done": None}, "no cap, said as none")
        supervisor.release(process)
        self.assertEqual(self.start(self.service()).request({"op": "cap"}), {"done": "none given"},
                         "a process no supervisor started is told none: its own environment's")

    def test_an_answer_that_says_retire_retires_its_process_once_let_go(self) -> None:
        supervisor = Supervisor(1, (self.service(),))
        self.addCleanup(supervisor.stop)
        process = supervisor.lease("child", "doc", {}, label="/w/doc.xbf")
        self.assertEqual(process.request({"op": "retire"}), {"done": "retire"})
        self.assertTrue(process.retired)
        supervisor.release(process)
        await_(lambda: not process.alive(), "its end, its stdin closed")
        self.assertEqual([(row["document"], row["reason"]) for row in supervisor.retired], [("/w/doc.xbf", "RSS")])

    def silent(self, **changes) -> tuple[Service, Path]:
        """A service whose child never says it is ready, and the folder it leaves its process's file in."""
        folder = Path(tempfile.mkdtemp(prefix="supervisor-"))
        self.addCleanup(shutil.rmtree, folder, True)
        return self.service("silent", str(folder), **changes), folder

    def test_a_child_that_never_says_ready_is_given_up_after_its_declared_seconds(self) -> None:
        service, _folder = self.silent(ready_seconds=0.5)
        supervisor = Supervisor(1, (service,))
        self.addCleanup(supervisor.stop)
        started, popen = [], subprocess.Popen

        def recorded(*args, **kwargs):
            started.append(popen(*args, **kwargs))
            return started[-1]

        with mock.patch.object(supervised.subprocess, "Popen", side_effect=recorded), \
                self.assertRaisesRegex(Gone, r"^the child /w/doc.xbf did not start: it never said it was ready in 0.5 s$") \
                as caught:
            supervisor.lease("child", "doc", {}, label="/w/doc.xbf")
        self.assertTrue(caught.exception.unready, "no request asks another to start")
        self.assertIsNotNone(started[0].poll(), "killed")
        self.assertEqual(supervisor.starting, set(), "its slot given back")

    def test_a_standby_that_never_says_ready_is_no_standby_and_the_log_says_so_once(self) -> None:
        service, _folder = self.silent()
        service = dataclasses.replace(service, standby=Standby((), "adopt", ready_seconds=0.5))
        supervisor = Supervisor(1, (service,))
        self.addCleanup(supervisor.stop)
        supervisor.enable_standby("child")
        with mock.patch("sys.stderr", new_callable=io.StringIO) as log:
            supervisor.stand("child", {})
            await_(lambda: supervisor.readying("child") is None, "the standby's start to be given up")
        self.assertIsNone(supervisor.standby("child"))
        self.assertEqual(log.getvalue(), "cad: no child standby: the child standby did not start: "
                                         "it never said it was ready in 0.5 s\n")

    def test_a_build_whose_worker_never_said_ready_is_refused_in_that_line_and_not_asked_again(self) -> None:
        from cad_server.engine.daemon import Daemon

        engine = Daemon(cap=1)
        self.addCleanup(engine.shutdown)
        launched: list = []

        def launch(service, key, label, environment, cwd, standby):
            launched.append(Path(label).name)
            raise Gone("the worker for a.py did not start: it never said it was ready in 300 s", unready=True)

        engine.supervisor.launch = launch
        sent: list = []
        engine.handle({"op": "build", "script": "/w/a.py", "env": {}}, sent.append)
        self.assertEqual(launched, ["a.py"], "asked once")
        self.assertEqual(sent, [{"failed": "the worker for a.py did not start: it never said it was ready in 300 s"}])

    def test_with_no_ready_seconds_a_silent_child_holds_its_lease_while_it_lives(self) -> None:
        import signal

        service, folder = self.silent()
        supervisor = Supervisor(1, (service,))
        self.addCleanup(supervisor.stop)
        failed: list = []

        def lease() -> None:
            try:
                supervisor.lease("child", "doc", {})
            except Gone as error:
                failed.append(error)

        def kill(count: int) -> None:
            await_(lambda: len(list(folder.iterdir())) == count, f"child {count} to start")
            [pid] = [path.name for path in folder.iterdir() if path.name not in killed]
            killed.add(pid)
            os.kill(int(pid), signal.SIGTERM)

        killed: set[str] = set()
        first, second = (threading.Thread(target=lease, daemon=True) for _ in range(2))
        first.start()
        await_(lambda: supervisor.starting == {("child", "doc")}, "the first lease to start its child")
        second.start()
        await_(lambda: supervisor.waiting("child") == 1, "the second lease to wait for the first's start")
        kill(1)
        first.join(30)
        self.assertIn("did not start", str(failed[0]))
        kill(2)  # the second lease's own child, started once the first gave its slot back
        second.join(30)
        self.assertEqual(len(failed), 2)

    def test_the_supervisor_s_stop_takes_a_standby_still_starting(self) -> None:
        # A standby reads nothing until it is ready, after its kernel loads (40 s on a fresh installation):
        # the daemon's stop takes it then too, never leaving it loading on its own after `cad stop`.
        service, folder = self.silent()
        service = dataclasses.replace(service, standby=Standby((), "adopt"))
        supervisor = Supervisor(1, (service,))
        started, popen = [], subprocess.Popen

        def recorded(*args, **kwargs):
            started.append(popen(*args, **kwargs))
            self.addCleanup(started[-1].kill)
            return started[-1]

        with mock.patch.object(supervised.subprocess, "Popen", side_effect=recorded):
            supervisor.enable_standby("child")
            supervisor.stand("child", {})
            await_(lambda: any(folder.iterdir()), "the standby to be started")
            supervisor.stop()
            await_(lambda: started[0].poll() is not None, "the standby still starting to be gone")
            await_(lambda: supervisor.readying("child") is None, "its start to be given up")
        self.assertIsNone(supervisor.standby("child"))
        self.assertEqual(supervisor.spawning, set())

    def test_a_stopped_child_ends_with_its_stdin_and_one_that_will_not_is_killed(self) -> None:
        process = self.start(self.service())
        process.stop()
        self.assertEqual(process.popen.returncode, 0, "its stdin's end is its own")
        deaf = self.start(self.service("deaf"))
        with mock.patch.object(supervised, "STOP_SECONDS", 0.2):
            deaf.stop()
        self.assertNotEqual(deaf.popen.returncode, 0, "killed")


if __name__ == "__main__":
    unittest.main()
