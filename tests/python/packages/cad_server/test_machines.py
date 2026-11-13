"""Watching a machine: each controller's reader against a fake of its protocol, the watch's numbered
readings, and the viewer's ``/api/v1/machines`` routes. Every fake records what it was sent, so each
test also holds the reader to reads alone: nothing that could move or change the machine."""

from __future__ import annotations

import http.server
import json
import socket
import socketserver
import threading
import time
import unittest

from cad_server.machines import Reading, parse_address
from cad_server.machines.grbl import GrblError, GrblReader, StatusParser
from cad_server.machines.linuxcnc import LinuxcncError, LinuxcncReader
from cad_server.machines.mtconnect import MtconnectError, MtconnectReader
from cad_server.machines.watch import Watches


class TcpFake:
    """A TCP server on loopback whose ``answer(data, connection)`` replies to what a client sends."""

    def __init__(self, answer):
        self.received: list[bytes] = []
        fake = self

        class Handler(socketserver.BaseRequestHandler):
            def handle(self):
                buffer = b""
                while True:
                    try:
                        chunk = self.request.recv(1024)
                    except OSError:
                        return
                    if not chunk:
                        return
                    fake.received.append(chunk)
                    buffer = answer(buffer + chunk, self.request)

        socketserver.ThreadingTCPServer.allow_reuse_address = True
        self.server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


class AddressTests(unittest.TestCase):
    def test_each_protocol_takes_its_port_and_options(self):
        self.assertEqual(str(parse_address("mtconnect://agent.local")), "mtconnect://agent.local:5000")
        self.assertEqual(parse_address("mtconnect://agent.local:5001/VMC-3Axis").options, {"device": "VMC-3Axis"})
        self.assertEqual(parse_address("LinuxCNC://mill:5008?password=secret").port, 5008)
        self.assertEqual(parse_address("grbl://fluidnc.local?units=inch").options, {"units": "inch"})

    def test_refusals_say_what_an_address_is(self):
        for text, said in (("", "is like"), ("http://agent:5000", "starts with"), ("grbl://", "names no host"),
                           ("grbl://host/path", "no path"), ("grbl://host?units=feet", "mm or inch"),
                           ("linuxcnc://host?speed=1", "takes the options"), ("grbl://host:port", "no port number"),
                           ("mtconnect://a/dev?device=other", "not both")):
            with self.subTest(text=text), self.assertRaisesRegex(ValueError, said):
                parse_address(text)


class GrblParserTests(unittest.TestCase):
    def test_machine_position_feed_speed_and_line(self):
        reading = StatusParser().parse("<Run|MPos:10.000,-20.500,3.250|FS:500,12000|Ln:42>")
        self.assertEqual(reading.axes, {"X": 10.0, "Y": -20.5, "Z": 3.25})
        self.assertEqual((reading.state, reading.detail, reading.feed, reading.spindle, reading.line),
                         ("running", "Run", 500.0, 12000.0, 42))
        self.assertTrue(reading.assumed and "millimetres" in reading.assumed[0], "the units it took are said")

    def test_a_work_position_waits_for_an_offset_then_is_the_machine_s(self):
        parser = StatusParser()
        self.assertIsNone(parser.parse("<Idle|WPos:1.000,2.000,3.000|FS:0,0>"), "no offset yet: no guess")
        reading = parser.parse("<Idle|WPos:1.000,2.000,3.000|FS:0,0|WCO:10.000,20.000,-5.000>")
        self.assertEqual(reading.axes, {"X": 11.0, "Y": 22.0, "Z": -2.0})
        self.assertEqual(parser.parse("<Idle|WPos:0.000,0.000,0.000|FS:0,0>").axes, {"X": 10.0, "Y": 20.0, "Z": -5.0})

    def test_inches_and_rotary_axes_and_states(self):
        reading = StatusParser(units="inch").parse("<Hold:0|MPos:1.000,0.000,0.000,90.000|F:10>")
        self.assertEqual(reading.axes, {"X": 25.4, "Y": 0.0, "Z": 0.0, "A": 90.0}, "a rotary axis stays in degrees")
        self.assertEqual((reading.state, reading.feed, reading.assumed), ("paused", 254.0, ()))
        for word, state in (("Idle", "idle"), ("Jog", "running"), ("Door:1", "paused"), ("Alarm", "alarm"), ("Sleep", "stopped")):
            self.assertEqual(StatusParser().parse(f"<{word}|MPos:0,0,0>").state, state)

    def test_what_is_not_a_report_is_refused(self):
        for text, said in (("ok", "not a GRBL status report"), ("<Dance|MPos:0,0,0>", "state it does not have"),
                           ("<Idle|FS:0,0>", "no position"), ("<Idle|MPos:a,b,c>", "not numbers")):
            with self.subTest(text=text), self.assertRaisesRegex(GrblError, said):
                StatusParser().parse(text)


class GrblReaderTests(unittest.TestCase):
    def test_it_sends_the_status_query_alone_and_skips_other_output(self):
        def answer(data, connection):
            for _ in range(data.count(b"?")):
                connection.sendall(b"[MSG:INFO: WiFi]\r\nok\r\n<Idle|MPos:1.000,2.000,3.000|FS:0,0>\r\n")
            return b""
        fake = TcpFake(answer)
        self.addCleanup(fake.close)
        reader = GrblReader(parse_address(f"grbl://127.0.0.1:{fake.port}"), timeout=2)
        reader.open()
        self.addCleanup(reader.close)
        for _ in range(3):
            self.assertEqual(reader.read().axes, {"X": 1.0, "Y": 2.0, "Z": 3.0})
        self.assertEqual(set(b"".join(fake.received)), {ord("?")}, "only the real-time status query is ever sent")

    def test_silence_is_an_error(self):
        fake = TcpFake(lambda data, connection: b"")
        self.addCleanup(fake.close)
        reader = GrblReader(parse_address(f"grbl://127.0.0.1:{fake.port}"), timeout=0.3)
        reader.open()
        self.addCleanup(reader.close)
        with self.assertRaisesRegex(GrblError, "no status report"):
            reader.read()


class LinuxcncFake:
    """``linuxcncrsh`` as its manual describes it, for the commands the reader may send."""

    def __init__(self, *, password="EMC", status="RUNNING", estop="OFF", machine="ON", units_kept="MM"):
        self.lines: list[str] = []
        self.units = "AUTO"

        def answer(data, connection):
            while b"\n" in data:
                line, _, data = data.partition(b"\n")
                text = line.decode().strip()
                self.lines.append(text)
                words = text.split()
                reply = None
                if words[0] == "hello":
                    reply = "HELLO ACK EMCNETSVR 1.1" if words[1] == password else "HELLO NAK"
                elif words[:2] == ["set", "linear_unit_conversion"]:
                    self.units = units_kept
                elif words[0] == "get":
                    reply = {"linear_unit_conversion": f"LINEAR_UNIT_CONVERSION {self.units}",
                             "abs_act_pos": "ABS_ACT_POS 100.0000 50.5000 -10.0000 0.0000 0.0000 0.0000 0.0000 0.0000 0.0000",
                             "program_status": f"PROGRAM_STATUS {status}", "estop": f"ESTOP {estop}",
                             "machine": f"MACHINE {machine}", "program_line": "PROGRAM_LINE 17",
                             "program": "PROGRAM /home/cnc/bracket.ngc"}.get(words[1], f"{words[1].upper()} NAK")
                if reply is not None:
                    connection.sendall(reply.encode() + b"\r\n")
            return data

        self.tcp = TcpFake(answer)
        self.port = self.tcp.port

    def close(self):
        self.tcp.close()


class LinuxcncReaderTests(unittest.TestCase):
    def reader(self, fake, query=""):
        reader = LinuxcncReader(parse_address(f"linuxcnc://127.0.0.1:{fake.port}{query}"), timeout=2)
        self.addCleanup(reader.close)
        return reader

    def test_a_running_program_and_only_reads_sent(self):
        fake = LinuxcncFake()
        self.addCleanup(fake.close)
        reader = self.reader(fake)
        reader.open()
        reading = reader.read()
        self.assertEqual((reading.axes["X"], reading.axes["Y"], reading.axes["Z"]), (100.0, 50.5, -10.0))
        self.assertEqual((reading.state, reading.line, reading.program), ("running", 17, "/home/cnc/bracket.ngc"))
        for line in fake.lines:
            self.assertTrue(line.startswith(("hello ", "get ")) or line == "set linear_unit_conversion mm",
                            f"{line!r} is not a read")

    def test_estop_and_power_and_password(self):
        for options, state in (({"estop": "ON"}, "alarm"), ({"machine": "OFF"}, "stopped"), ({"status": "PAUSED"}, "paused")):
            fake = LinuxcncFake(**options)
            self.addCleanup(fake.close)
            reader = self.reader(fake)
            reader.open()
            self.assertEqual(reader.read().state, state)
        fake = LinuxcncFake(password="secret")
        self.addCleanup(fake.close)
        with self.assertRaisesRegex(LinuxcncError, "password"):
            self.reader(fake).open()
        self.reader(fake, "?password=secret").open()

    def test_units_it_cannot_set_are_refused(self):
        fake = LinuxcncFake(units_kept="INCH")
        self.addCleanup(fake.close)
        with self.assertRaisesRegex(LinuxcncError, "millimetres"):
            self.reader(fake).open()


PROBE = b"""<?xml version="1.0"?>
<MTConnectDevices xmlns="urn:mtconnect.org:MTConnectDevices:1.7">
 <Devices>
  <Device id="d1" name="VMC" uuid="vmc-1">
   <DataItems><DataItem id="estop" type="EMERGENCY_STOP" category="EVENT"/></DataItems>
   <Components>
    <Axes id="axes">
     <Components>
      <Linear id="x" name="X"><DataItems>
       <DataItem id="Xcmd" type="POSITION" subType="COMMANDED" category="SAMPLE" units="MILLIMETER"/>
       <DataItem id="Xwork" type="POSITION" subType="ACTUAL" coordinateSystem="WORK" category="SAMPLE" units="MILLIMETER"/>
       <DataItem id="Xabs" type="POSITION" subType="ACTUAL" coordinateSystem="MACHINE" category="SAMPLE" units="MILLIMETER"/>
      </DataItems></Linear>
      <Linear id="y" name="Y"><DataItems>
       <DataItem id="Yabs" type="POSITION" subType="ACTUAL" category="SAMPLE" units="MILLIMETER"/>
      </DataItems></Linear>
      <Linear id="z" name="Z"><DataItems>
       <DataItem id="Zabs" type="POSITION" subType="ACTUAL" category="SAMPLE" units="MILLIMETER"/>
      </DataItems></Linear>
      <Rotary id="c" name="C"><DataItems>
       <DataItem id="Cang" type="ANGLE" subType="ACTUAL" category="SAMPLE" units="DEGREE"/>
      </DataItems></Rotary>
      <Rotary id="s" name="S1"><DataItems>
       <DataItem id="Sspeed" type="ROTARY_VELOCITY" subType="ACTUAL" category="SAMPLE" units="REVOLUTION/MINUTE"/>
       <DataItem id="Sang" type="ANGLE" category="SAMPLE" units="DEGREE"/>
      </DataItems></Rotary>
     </Components>
    </Axes>
    <Controller id="cont"><Components><Path id="path"><DataItems>
     <DataItem id="exec" type="EXECUTION" category="EVENT"/>
     <DataItem id="feed" type="PATH_FEEDRATE" subType="ACTUAL" category="SAMPLE" units="MILLIMETER/SECOND"/>
     <DataItem id="prog" type="PROGRAM" category="EVENT"/>
     <DataItem id="ln" type="LINE_NUMBER" category="EVENT"/>
    </DataItems></Path></Components></Controller>
   </Components>
  </Device>
 </Devices>
</MTConnectDevices>"""

CURRENT = b"""<?xml version="1.0"?>
<MTConnectStreams xmlns="urn:mtconnect.org:MTConnectStreams:1.7"><Streams>
 <DeviceStream name="VMC" uuid="vmc-1">
  <ComponentStream component="Device" componentId="d1"><Events><EmergencyStop dataItemId="estop">ARMED</EmergencyStop></Events></ComponentStream>
  <ComponentStream component="Linear" name="X" componentId="x"><Samples>
   <Position dataItemId="Xcmd" subType="COMMANDED">999</Position>
   <Position dataItemId="Xwork" subType="ACTUAL">5</Position>
   <Position dataItemId="Xabs" subType="ACTUAL">120.5</Position></Samples></ComponentStream>
  <ComponentStream component="Linear" name="Y" componentId="y"><Samples><Position dataItemId="Yabs">-40</Position></Samples></ComponentStream>
  <ComponentStream component="Linear" name="Z" componentId="z"><Samples><Position dataItemId="Zabs">UNAVAILABLE</Position></Samples></ComponentStream>
  <ComponentStream component="Rotary" name="C" componentId="c"><Samples><Angle dataItemId="Cang">45</Angle></Samples></ComponentStream>
  <ComponentStream component="Rotary" name="S1" componentId="s"><Samples>
   <RotaryVelocity dataItemId="Sspeed">8000</RotaryVelocity><Angle dataItemId="Sang">12</Angle></Samples></ComponentStream>
  <ComponentStream component="Path" componentId="path">
   <Samples><PathFeedrate dataItemId="feed">25</PathFeedrate></Samples>
   <Events><Execution dataItemId="exec">ACTIVE</Execution><Program dataItemId="prog">O1234</Program><LineNumber dataItemId="ln">88</LineNumber></Events>
  </ComponentStream>
 </DeviceStream>
</Streams></MTConnectStreams>"""


class AgentFake:
    """An MTConnect agent's HTTP side: ``probe`` and ``current``, with every request recorded."""

    def __init__(self, probe=PROBE, current=CURRENT):
        self.paths: list[tuple[str, str]] = []
        fake = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                fake.paths.append(("GET", self.path))
                body = {"/probe": probe, "/current": current, "/VMC/probe": probe, "/VMC/current": current}.get(self.path)
                self.send_response(200 if body else 404)
                self.send_header("content-type", "application/xml")
                self.end_headers()
                self.wfile.write(body or b"")

            def do_POST(self):  # an agent takes PUTs and POSTs only where it is configured to; a reader sends none
                fake.paths.append(("POST", self.path))
                self.send_response(405)
                self.end_headers()

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


class MtconnectTests(unittest.TestCase):
    def test_axes_in_machine_coordinates_state_feed_spindle(self):
        agent = AgentFake()
        self.addCleanup(agent.close)
        reader = MtconnectReader(parse_address(f"mtconnect://127.0.0.1:{agent.port}"))
        reader.open()
        reading = reader.read()
        self.assertEqual(reading.axes, {"X": 120.5, "Y": -40.0, "C": 45.0},
                         "machine coordinates first, an unavailable axis left out, the spindle never an axis")
        self.assertEqual((reading.state, reading.detail, reading.feed, reading.spindle, reading.line, reading.program),
                         ("running", "ACTIVE", 1500.0, 8000.0, 88, "O1234"))
        self.assertEqual({method for method, _ in agent.paths}, {"GET"})
        self.assertEqual({path for _, path in agent.paths}, {"/probe", "/current"})

    def test_a_device_by_its_path_and_one_it_does_not_have(self):
        agent = AgentFake()
        self.addCleanup(agent.close)
        reader = MtconnectReader(parse_address(f"mtconnect://127.0.0.1:{agent.port}/VMC"))
        reader.open()
        self.assertEqual(reader.read().axes["X"], 120.5)
        with self.assertRaisesRegex(MtconnectError, "answered 404"):
            MtconnectReader(parse_address(f"mtconnect://127.0.0.1:{agent.port}/Lathe")).open()

    def test_several_devices_need_one_named(self):
        two = PROBE.replace(b"</Devices>", b'<Device id="d2" name="Lathe"><DataItems/></Device></Devices>')
        agent = AgentFake(probe=two)
        self.addCleanup(agent.close)
        with self.assertRaisesRegex(MtconnectError, r"several devices \(Lathe, VMC\)"):
            MtconnectReader(parse_address(f"mtconnect://127.0.0.1:{agent.port}")).open()

    def test_estop_is_an_alarm_and_bad_units_refused(self):
        agent = AgentFake(current=CURRENT.replace(b">ARMED<", b">TRIGGERED<"))
        self.addCleanup(agent.close)
        reader = MtconnectReader(parse_address(f"mtconnect://127.0.0.1:{agent.port}"))
        reader.open()
        self.assertEqual(reader.read().state, "alarm")
        agent = AgentFake(probe=PROBE.replace(b'id="Yabs" type="POSITION" subType="ACTUAL" category="SAMPLE" units="MILLIMETER"',
                                              b'id="Yabs" type="POSITION" subType="ACTUAL" category="SAMPLE" units="INCH"'))
        self.addCleanup(agent.close)
        reader = MtconnectReader(parse_address(f"mtconnect://127.0.0.1:{agent.port}"))
        reader.open()
        with self.assertRaisesRegex(MtconnectError, "axis Y is in INCH"):
            reader.read()

    def test_an_unreachable_agent_says_so(self):
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        with self.assertRaisesRegex(MtconnectError, "cannot reach the agent"):
            MtconnectReader(parse_address(f"mtconnect://127.0.0.1:{port}"), timeout=0.5).open()


class ScriptedReader:
    """A reader that answers ``readings`` in turn (an exception is raised), then the last forever."""

    def __init__(self, readings):
        self.readings, self.opened, self.closed = list(readings), 0, 0

    def open(self):
        self.opened += 1

    def close(self):
        self.closed += 1

    def read(self):
        item = self.readings.pop(0) if len(self.readings) > 1 else self.readings[0]
        if isinstance(item, Exception):
            raise item
        return item


def at(x):
    return Reading(axes={"X": x}, state="running", detail="Run")


class WatchTests(unittest.TestCase):
    def test_readings_are_numbered_and_waited_on(self):
        reader = ScriptedReader([at(1), at(2), at(2)])
        watches = Watches(reader_for=lambda address: reader, period=0.01, retry=0.01)
        self.addCleanup(watches.close)
        first = watches.start("grbl://mill")
        watch = watches.get(first["id"])
        state = watch.wait(-1, 2)
        while state["reading"] is None or state["reading"]["axes"]["X"] != 2:
            state = watch.wait(state["version"], 2)
        self.assertTrue(state["connected"])
        settled = watch.wait(state["version"], 0.2)
        self.assertEqual(settled["version"], state["version"], "an unchanged reading is no new version")
        self.assertEqual(watches.start("grbl://mill:23")["id"], first["id"], "one address, one watch")

    def test_a_lost_controller_is_said_and_read_again(self):
        reader = ScriptedReader([ConnectionError("gone"), at(5)])
        watches = Watches(reader_for=lambda address: reader, period=0.01, retry=0.01)
        self.addCleanup(watches.close)
        watch = watches.get(watches.start("mtconnect://agent")["id"])
        state = watch.wait(-1, 2)
        seen_error = state["error"] == "gone"
        while not (state["connected"] and state["reading"]):
            state = watch.wait(state["version"], 2)
            seen_error = seen_error or state["error"] == "gone"
        self.assertTrue(seen_error)
        self.assertGreaterEqual(reader.opened, 2)
        self.assertEqual(state["reading"]["axes"], {"X": 5.0})

    def test_a_watch_no_page_asks_after_stops(self):
        reader = ScriptedReader([at(1)])
        watches = Watches(reader_for=lambda address: reader, period=0.01, retry=0.01, idle=0.2)
        ident = watches.start("grbl://mill")["id"]
        watch = watches.watches[ident]
        watch.thread.join(timeout=3)
        self.assertFalse(watch.thread.is_alive(), "its thread ends")
        self.assertIsNone(watches.get(ident))


if __name__ == "__main__":
    unittest.main()
