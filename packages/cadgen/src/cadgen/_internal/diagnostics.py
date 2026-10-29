"""Read-only doctor report, schema 1. No setup, pruning, engine start or work requests.

A project probe imports only cadgen in the explicitly named Python. Current engine probes send only
hello; separately discovered legacy installation endpoints receive read-only status. Both use
bounded children so a broken listener cannot hang doctor. POSIX hello uses the normal
transport's temporary FIFO pair, removed on close; no persistent state is changed.

A project, an engine and this CLI meet by protocol, document format and native line, never by
release (``cadgen.engine.runtime.refusal``): what does not meet is ``incompatible`` (exit 3, the
finding naming what differs); a release apart alone is a warning, ``release_behind``, whose remedy
is the nudge the engine gives a build.
"""
from __future__ import annotations

import json
import os
import re
import socket
import stat
import subprocess
import sys
from pathlib import Path

from cadgen._internal import doctor_files, installations

SCHEMA = 1
PROBE_SECONDS = 3
MAX_ENGINES = 16
MAX_RECORDS = 128
# Supplied by the application composition root; the report knows no provider.
HOST_INVENTORY = None
# Suppress import chatter, including custom cadgen imports; never return stderr or exception text.
# What the project meets an engine by (``runtime.identity``) where its cadgen says it, else its
# protocol alone (a cadgen before 0.8.3); no kernel is imported for either.
_PROJECT_PROBE = """
import contextlib, io, json, sys
result = {'status': 'unusable'}
with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
    try:
        import cadgen
        result = {'status': 'ok', 'release': cadgen.__version__, 'path': cadgen.__file__,
                  'python': sys.executable, 'python_version': sys.version.split()[0]}
    except ModuleNotFoundError as error:
        result = {'status': 'missing' if error.name == 'cadgen' else 'unusable'}
    except BaseException:
        pass
    if result['status'] == 'ok':
        try:
            from cadgen.engine import runtime
            result['meets'] = runtime.identity()
        except BaseException:
            try:
                from cadgen.engine import daemon
                result['meets'] = {'protocol': daemon.PROTOCOL}
            except BaseException:
                pass
sys.__stdout__.write('CADGEN_DIAGNOSTIC=' + json.dumps(result) + '\\n')
"""
_FORMAT = re.compile(r"xbf/[0-9]{1,4}")
_WORD = re.compile(r"[0-9A-Za-z._+-]{1,64}")


def _child(command: list[str], *, seconds: float = PROBE_SECONDS) -> dict:
    try:
        done = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace",
                              timeout=seconds, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
    except subprocess.TimeoutExpired:
        return {"status": "timeout"}
    except OSError:
        return {"status": "unusable"}
    if done.returncode or len(done.stdout) > 65536:
        return {"status": "unusable"}
    try:
        line = done.stdout.splitlines()[-1]
        data = json.loads(line.removeprefix("CADGEN_DIAGNOSTIC=")) if line.startswith("CADGEN_DIAGNOSTIC=") else None
        return data if isinstance(data, dict) else {"status": "unusable"}
    except (ValueError, IndexError, RecursionError):
        return {"status": "unusable"}


def project(python: str) -> dict:
    path = os.path.abspath(os.path.expanduser(python))
    data = _child([path, "-B", "-P", "-c", _PROJECT_PROBE])
    result = {"requested_python": path, "status": data.get("status", "unusable")}
    if result["status"] not in {"ok", "missing", "unusable", "timeout"}:
        result["status"] = "unusable"
    if result["status"] == "ok":
        release = data.get("release")
        if not isinstance(release, str) or not installations.VERSION.fullmatch(release):
            return {**result, "status": "unusable"}
        result["release"] = release
        for key in ("path", "python", "python_version"):
            value = data.get(key)
            if isinstance(value, str) and len(value) <= 4096:
                result[key] = value
        meets = _meets(data.get("meets"))
        if meets is not None:
            result["meets"] = meets
    return result


def _meets(found) -> dict | None:
    """What a side says it meets another by (``runtime.identity``: ``protocol``, ``writes``,
    ``reads``, ``native``), only in the shapes those take, so nothing else a probed process or a
    listener says escapes; None without a protocol."""
    if not isinstance(found, dict) or type(found.get("protocol")) is not int:
        return None
    meets = {"protocol": found["protocol"]}
    if isinstance(found.get("writes"), str) and _FORMAT.fullmatch(found["writes"]):
        meets["writes"] = found["writes"]
    reads = found.get("reads")
    if (isinstance(reads, list) and 0 < len(reads) <= 16
            and all(isinstance(name, str) and _FORMAT.fullmatch(name) for name in reads)):
        meets["reads"] = list(reads)
    native = found.get("native")
    if isinstance(native, dict):
        line = native.get("ocp_line")
        if (all(isinstance(native.get(key), str) and _WORD.fullmatch(native[key]) for key in ("system", "arch"))
                and (line is None or isinstance(line, str) and _WORD.fullmatch(line))):
            meets["native"] = {"system": native["system"], "arch": native["arch"], "ocp_line": line}
    return meets


def _list(folder: Path) -> tuple[list[Path], str]:
    try:
        with os.scandir(folder) as entries:
            paths = []
            for index, entry in enumerate(entries):
                if entry.name.endswith(".json"):
                    paths.append(Path(entry.path))
                if index >= MAX_RECORDS:
                    return paths[:MAX_RECORDS], "limited"
        return sorted(paths), "ok"
    except FileNotFoundError:
        return [], "missing"
    except OSError:
        return [], "unreadable"


def registered(state: Path) -> dict:
    folder = state / "installations"
    paths, status = _list(folder)
    found = []
    for path in paths:
        data, state_of_file = doctor_files.read(path)
        item = {"path": str(path), "status": state_of_file}
        if data is not None:
            parsed = installations._parse(json.dumps(data).encode())
            if parsed is None or parsed["version"] != path.stem or not installations.VERSION.fullmatch(path.stem):
                item["status"] = "invalid"
            else:
                item.update({key: parsed[key] for key in ("version", "python", "cadgen", "prefix")})
                # Valid means the registered paths exist, not that every interpreter was executed.
                item["status"] = "valid" if installations.alive(parsed) else "stale"
        found.append(item)
    return {"path": str(folder), "status": status, "records": found}


def _listener(port: int) -> str:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.2):
            return "conflicting_listener"
    except ConnectionRefusedError:
        return "missing"
    except (socket.timeout, TimeoutError):
        # A listener on the loopback answers at once; a connect that times out there is a port
        # nobody serves, which some Windows firewalls drop instead of refusing.
        return "missing"
    except OSError:
        return "unknown"


def _read_port_file(address: Path, expected) -> bytes | None:
    """Bounded descriptor read; validate the opened file against the non-following stat."""
    handle = os.open(address, os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_NOFOLLOW", 0))
    try:
        found = os.fstat(handle)
        if (not stat.S_ISREG(found.st_mode) or (found.st_dev, found.st_ino) != (expected.st_dev, expected.st_ino)
                or found.st_uid != expected.st_uid or found.st_size > 1024):
            return None
        with os.fdopen(handle, "rb", closefd=False) as stream:
            data = stream.read(1025)
        return data if len(data) <= 1024 else None
    finally:
        os.close(handle)


def _open_endpoint(address: Path):
    """Only this user's real FIFO/port file; no link following or permission repair."""
    from cadgen.engine import daemon, door

    try:
        info = address.lstat()
        if (stat.S_ISLNK(info.st_mode) or (hasattr(os, "getuid") and info.st_uid != os.getuid())
                or (os.name != "nt" and info.st_mode & 0o022)):
            return None, None, "invalid_endpoint"
        if daemon.WINDOWS:
            if not stat.S_ISREG(info.st_mode) or info.st_size > 1024:
                return None, None, "invalid_endpoint"
            raw = _read_port_file(address, info)
            if raw is None:
                return None, None, "invalid_endpoint"
            parts = raw.decode("ascii").split()
            transport = doctor_files._port(parts[0]) if len(parts) == 2 else None
            if transport is None or not re.fullmatch(r"[0-9a-f]{32}", parts[1]):
                return None, None, "invalid_endpoint"
            sock = socket.create_connection(("127.0.0.1", transport), timeout=0.5)
            try:
                sock.settimeout(0.5)
                stream = sock.makefile("rwb")
            except BaseException:
                sock.close()
                raise
            return door.Connection(stream, stream, stream, sock), parts[1], "ok"
        if not stat.S_ISFIFO(info.st_mode):
            return None, None, "invalid_endpoint"
        if not door.answering(address):
            return None, None, "stale_endpoint"
        connection = door.dial(address, timeout=0.5, repair=False)
        return connection, None, "ok" if connection else "stale_endpoint"
    except PermissionError:
        return None, None, "unreadable"
    except FileNotFoundError:
        return None, None, "stale_endpoint"
    except (OSError, ValueError, UnicodeError):
        return None, None, "unknown_protocol"


def _probe_port(port: int) -> dict:
    """Runs in a bounded child. A refused hello never becomes permission to send status/work."""
    from cadgen.engine import client, daemon, runtime

    folder = daemon.state_dir()
    if not folder.exists():
        return {"status": _listener(port)}
    if daemon.folder_refusal(folder):
        return {"status": "unreadable"}
    address = folder / (daemon._tag(port=port) + (".port" if daemon.WINDOWS else ".door"))
    if not os.path.lexists(address):
        return {"status": _listener(port)}
    connection = None
    discovery = {}
    try:
        message = client.hello(port=port)
        connection, token, status = _open_endpoint(address)
        if connection is None:
            if status == "stale_endpoint":
                listener = _listener(port)
                status = "stale_endpoint" if listener == "missing" else listener
            return {"status": status}
        if token is not None:
            # Windows authenticates the token prefix before reading the rest of the line.
            message = {"token": token, **message}
        discovery = {"discovery": "port_endpoint", "endpoint": str(address)}
        connection.writer.write((json.dumps(message) + "\n").encode())
        connection.writer.flush()
        answer = json.loads(connection.reader.readline(65537))
        if not isinstance(answer, dict):
            return {"status": "unknown_protocol", **discovery}
        identity = {}
        release = answer.get("release")
        if isinstance(release, str) and installations.VERSION.fullmatch(release):
            identity["release"] = release
        for key in ("protocol", "port"):
            if type(answer.get(key)) is int:
                identity[key] = answer[key]
        meets = _meets(answer)
        if meets is not None:
            identity.update({key: value for key, value in meets.items() if key != "protocol"})
        if "protocol" not in identity:
            return {"status": "unknown_protocol", **discovery}
        # The rule a client greets by (``runtime.refusal``): never the release.
        refused = runtime.refusal(message, answer, port=port)
        answered = (not answer.get("failed") and answer.get("ok") is True and answer.get("port") == port
                    and isinstance(answer.get("instance"), str) and bool(answer["instance"]))
        if answered and refused is None:
            return {"status": "compatible", **identity, **discovery}
        reason = refused.what if refused is not None else "port" if identity.get("port") != port else "refused"
        return {"status": "incompatible", "reason": reason, **identity, **discovery}
    except PermissionError:
        return {"status": "unreadable", **discovery}
    except (OSError, ValueError, TypeError, RecursionError):
        return {"status": "unknown_protocol", **discovery}
    finally:
        if connection is not None:
            connection.close()


def _legacy_identity(answer) -> dict | None:
    """The only fields allowed out of a legacy status response; documents/tokens never escape. The
    engine's own reading of one (``cadgen.engine.client``), which ``cadgen status`` and ``stop`` use."""
    from cadgen.engine import client

    return client._legacy_identity(answer)


def _probe_legacy_endpoint(name: str) -> dict:
    """One status request to an installation-hashed endpoint selected by legacy_endpoints()."""
    from cadgen.engine import daemon

    suffix = ".port" if daemon.WINDOWS else ".door"
    if not re.fullmatch(r"[0-9a-f]{12}" + re.escape(suffix), name):
        return {"status": "invalid_endpoint"}
    folder = daemon.state_dir()
    if daemon.folder_refusal(folder):
        return {"status": "unreadable"}
    connection = None
    try:
        connection, token, status = _open_endpoint(folder / name)
        if connection is None:
            return {"status": status}
        message = {"op": "status"}
        if token is not None:
            message = {"token": token, **message}
        connection.writer.write((json.dumps(message) + "\n").encode())
        connection.writer.flush()
        line = connection.reader.readline(doctor_files.MAX_BYTES + 1)
        if len(line) > doctor_files.MAX_BYTES:
            return {"status": "too_large"}
        identity = _legacy_identity(json.loads(line))
        return {"status": "incompatible", **identity} if identity else {"status": "unknown_protocol"}
    except PermissionError:
        return {"status": "unreadable"}
    except (OSError, ValueError, TypeError, RecursionError):
        return {"status": "unknown_protocol"}
    finally:
        if connection is not None:
            connection.close()


def legacy_endpoints() -> dict:
    """Scan the private directory once; never send legacy status to a port-derived endpoint."""
    from cadgen.engine import daemon

    folder = daemon.state_dir()
    result = {"path": str(folder), "status": "ok", "records": [], "current_ports": []}
    if not folder.exists():
        return {**result, "status": "missing"}
    if daemon.folder_refusal(folder):
        return {**result, "status": "unreadable"}
    suffix = ".port" if daemon.WINDOWS else ".door"
    candidates = []
    try:
        with os.scandir(folder) as entries:
            for index, entry in enumerate(entries):
                if index >= MAX_RECORDS:
                    result["status"] = "limited"
                    break
                if re.fullmatch(r"[0-9a-f]{12}" + re.escape(suffix), entry.name):
                    candidates.append(entry.name)
    except OSError:
        return {**result, "status": "unreadable"}
    if not candidates:
        return result
    # A bounded hash table also recognizes unrecorded modern ports. No filesystem scan per port.
    current = {daemon._tag(port=port): port for port in range(1, 65536)}
    legacy = []
    for name in sorted(candidates):
        port = current.get(name[:-len(suffix)])
        if port is not None:
            result["current_ports"].append(port)
        else:
            legacy.append(name)
    if len(legacy) > MAX_ENGINES:
        result["status"] = "limited"
    for name in legacy[:MAX_ENGINES]:
        code = ("import json,sys; from cadgen._internal.diagnostics import _probe_legacy_endpoint; "
                "result=_probe_legacy_endpoint(sys.argv[1]); "
                "sys.__stdout__.write('CADGEN_DIAGNOSTIC='+json.dumps(result)+'\\n')")
        data = _child([sys.executable, "-B", "-P", "-c", code, name])
        status = data.get("status")
        allowed = {"incompatible", "stale_endpoint", "invalid_endpoint", "unreadable", "unknown_protocol",
                   "too_large", "timeout", "unusable"}
        record = {"path": str(folder / name), "status": status if status in allowed else "unknown_protocol",
                  "discovery": "legacy_private_endpoint", "protocol": "legacy-status"}
        if record["status"] == "incompatible":
            identity = _legacy_identity({"ok": True, "serving": {"port": data.get("port")},
                                         "version": data.get("release"), "pid": data.get("pid"),
                                         "installation": data.get("installation")})
            if identity is None:
                record["status"] = "unknown_protocol"
            else:
                record.update(identity)
        result["records"].append(record)
    return result


def engine(port: int) -> dict:
    from cadgen.engine import daemon

    address = daemon.state_dir() / (daemon._tag(port=port) + (".port" if daemon.WINDOWS else ".door"))
    present = os.path.lexists(address)
    code = ("import contextlib,io,json,sys; "
            "from cadgen._internal.diagnostics import _probe_port; "
            "result=_probe_port(int(sys.argv[1])); "
            "sys.__stdout__.write('CADGEN_DIAGNOSTIC='+json.dumps(result)+'\\n')")
    data = _child([sys.executable, "-B", "-P", "-c", code, str(port)])
    allowed = {"compatible", "incompatible", "unknown_protocol", "invalid_endpoint", "stale_endpoint", "missing",
               "conflicting_listener", "unknown", "unreadable", "timeout", "unusable"}
    result = {"port": port, "status": data.get("status") if data.get("status") in allowed else "unknown"}
    release = data.get("release")
    if isinstance(release, str) and installations.VERSION.fullmatch(release):
        result["release"] = release
    if type(data.get("protocol")) is int:
        result["protocol"] = data["protocol"]
    meets = _meets({"protocol": 0, **{key: data.get(key) for key in ("writes", "reads", "native")}})
    result.update({key: value for key, value in (meets or {}).items() if key != "protocol"})
    if result["status"] == "incompatible" and data.get("reason") in {"protocol", "format", "native", "port", "refused"}:
        result["reason"] = data["reason"]
    if present or data.get("discovery") == "port_endpoint":
        # Preserve a possibly attempted hello even if the child times out before returning metadata.
        result["discovery"] = "port_endpoint"
        result["endpoint"] = str(address)
    if type(data.get("port")) is int and data["port"] != port:
        result["advertised_port"] = data["port"]
    return result


def _sentence(text: str) -> str:
    """A remedy's words as the report's remedies read: a sentence."""
    return text[:1].upper() + text[1:] + ("" if text.endswith(".") else ".")


def _releases(theirs: str, ours: str) -> int | None:
    """-1, 0 or 1 as release ``theirs`` is older than, the same as or newer than ``ours``
    (``daemon.rank``); None where either is no version."""
    from cadgen.engine.daemon import rank

    first, second = rank(theirs), rank(ours)
    return None if first is None or second is None else (first > second) - (first < second)


def report(python: str | None, skill: Path | None, *, requested_skill: str | None = None) -> dict:
    import cadgen
    from cadgen.cli import _PIN_RE, _RUN_PIN_RE
    from cadgen.engine import daemon, runtime
    from cadgen.viewer.recents import state_dir

    release = cadgen.__version__
    state = state_dir()
    installation_data = registered(state)
    named = os.environ.get(installations.NAME_ENV)
    named = named if named and installations.VERSION.fullmatch(named) else None
    if named is None:
        for record in installation_data["records"]:
            if (record["status"] == "valid" and installations._same_place(record["prefix"], sys.prefix)
                    and (record["version"] == release or record["version"].startswith(release + "-dev."))):
                named = record["version"]
    if named is None and not installations.editable():
        named = release
    ours = runtime.identity()
    current = {"release": release, "installation": named, "python": sys.executable,
               "python_version": sys.version.split()[0], "path": str(Path(cadgen.__file__).resolve()),
               "executable": os.path.abspath(sys.argv[0]), "proxy": installations.proxy_path(),
               "meets": {key: ours[key] for key in ("protocol", "writes", "reads", "native")}}
    issues = []

    def issue(code: str, detail: str, remedy: str, *, error: bool = False, incompatible: bool = False):
        issues.append({"code": code, "severity": "error" if error or incompatible else "warning", "detail": detail,
                       "remedy": remedy, "exit_code": 3 if incompatible else 5 if error else 0})

    pin = None
    skill_unreadable = False
    if skill:
        contents, status = doctor_files.read_bytes(skill)
        if contents is None:
            skill_unreadable = True
        else:
            try:
                text = contents.decode("utf-8")
                match = _PIN_RE.search(text) or _RUN_PIN_RE.search(text)
                pin = match.group("pin") if match else None
            except UnicodeError:
                skill_unreadable = True
    if pin is not None and not installations.VERSION.fullmatch(pin):
        pin = None
        skill_state = "invalid"
    else:
        skill_state = "unreadable" if skill_unreadable else "pinned" if pin else "unpinned" if skill else "missing" if requested_skill else "not_requested"
    skill_data = {"path": str(skill) if skill else None, "release": pin, "status": skill_state}
    if skill_state in {"invalid", "missing", "unreadable"}:
        issue("skill_unavailable", "The requested skill or its release pin cannot be read.",
              "Pass a readable SKILL.md or its directory.", error=True)
    if pin and pin not in {release, current["installation"]}:
        # Another installation's command, not an incompatibility: the skill runs its own cadgen.
        issue("skill_mismatch", f"The requested skill pins cadgen {pin}; this CLI is cadgen "
                                f"{current['installation'] or release}.",
              f"Run the skill's cadgen +{pin} doctor to check the installation the skill runs.")
    project_data = project(python) if python is not None else {"status": "not_requested"}
    if python is not None and project_data["status"] != "ok":
        issue("project_unavailable", "The requested Python cannot import cadgen.",
              f"Check that interpreter path and install cadgen=={release} in that environment.", error=True)
    for item in installation_data["records"]:
        if item["status"] != "valid":
            issue("installation_" + item["status"], "An installation record is stale or cannot be read: " + item["path"],
                  "Re-run that release's cadgen doctor to register it; inspect stale records before doctor --prune.")
    if installation_data["status"] in {"limited", "unreadable"}:
        issue("installation_inventory_incomplete", "The installation inventory is incomplete.",
              "Inspect the registered installation folder locally; no environments were scanned.")
    hosts = HOST_INVENTORY() if HOST_INVENTORY else {
        "coverage": "No host inventory capability was supplied.", "sources": []}
    ports = set()
    try:
        selected = daemon.selected_port()
        ports.add(selected)
    except ValueError:
        selected = None
        issue("invalid_port", "CADGEN_PORT is invalid.", "Set CADGEN_PORT to an integer from 1 to 65535.", error=True)
    paths, records_state = _list(state / "engines")
    records = []
    for path in paths:
        data, status = doctor_files.read(path)
        port = doctor_files._port(data.get("port")) if data else None
        item = {"path": str(path), "status": status if data is None else "known" if port and data.get("schema") == 3 else "legacy" if port else "invalid"}
        if port:
            item["port"] = port
            ports.add(port)
        records.append(item)
        if item["status"] in {"invalid", "unreadable", "too_large", "legacy"}:
            issue("engine_record_" + item["status"], "An engine record is invalid, unreadable or from an older schema: " + str(path),
                  "Inspect the record locally; it is historical evidence and never selects or starts a server.")
    for source in hosts["sources"]:
        if source.get("port"):
            ports.add(source["port"])
        if source["status"] in {"invalid", "unreadable", "unknown", "limited", "too_large"}:
            issue("host_" + source["status"], "A supported host source could not be fully interpreted: " + source["path"],
                  "Inspect that source locally; the inventory does not establish what the host has loaded.")
    legacy = legacy_endpoints()
    ports.update(legacy["current_ports"])
    ports.update(record["port"] for record in legacy["records"] if record["status"] == "incompatible")
    if legacy["status"] in {"limited", "unreadable"}:
        issue("endpoint_inventory_incomplete", "The private-endpoint inventory reached its bound or could not be read.",
              "Inspect this user's private engine directory locally; the inventory may omit running engines.")
    for record in legacy["records"]:
        if record["status"] not in {"incompatible", "stale_endpoint"}:
            issue("legacy_endpoint_" + record["status"], "A legacy endpoint could not be identified: " + record["path"],
                  "The listener's identity and serving port remain unproven; inspect it locally without sending work.")
    ordered = sorted(ports, key=lambda port: (port != selected, port))
    engines = [engine(port) for port in ordered[:MAX_ENGINES]]
    for item in engines:
        evidence = [record for record in legacy["records"]
                    if record["status"] == "incompatible" and record["port"] == item["port"]]
        if not evidence:
            continue
        item["legacy_endpoints"] = evidence
        if item["port"] in legacy["current_ports"]:
            # A timed-out child may have sent hello before it could return its provenance.
            item["discovery"] = "port_endpoint"
        # A modern hello attempt, including refusal, always keeps its own result.
        if (item.get("discovery") == "port_endpoint"
                or item["status"] not in {"missing", "stale_endpoint", "conflicting_listener", "unknown"}):
            issue("endpoint_port_conflict", f"Legacy evidence shares port {item['port']} with a current or inconclusive probe.",
                  "Keep the current probe result; inspect the separate legacy evidence before changing any engine.")
            continue
        item.update({"status": "incompatible", "protocol": "legacy-status", "discovery": "legacy_private_endpoint"})
        if len(evidence) == 1:
            item.update({key: evidence[0][key] for key in ("release", "pid", "installation") if key in evidence[0]})
        else:
            issue("legacy_port_ambiguous", f"Several legacy endpoints claim serving port {item['port']}.",
                  "Use their separate endpoint identities; no single installation is proven for this port.")
    if len(ordered) > MAX_ENGINES or records_state in {"limited", "unreadable"}:
        issue("engine_inventory_incomplete", "The known-engine inventory reached its bound or could not be read.",
              "Inspect the engine records locally and repeat for a specific CADGEN_PORT.")
    for item in engines:
        item["selected"] = item["port"] == selected
        item["expected_release"] = release
        item["configured_releases"] = sorted({source["release"] for source in hosts["sources"]
                                               if source.get("release") and source.get("port") == item["port"]
                                               and source.get("kind") != "cached_plugin"})
        item["records"] = [record["path"] for record in records if record.get("port") == item["port"]]
        if item["selected"] and item["status"] == "incompatible":
            issue("engine_incompatible", *_engine_incompatible(item, ours), incompatible=True)
        elif item["selected"] and item["status"] == "compatible":
            order = _releases(item.get("release") or "", release)
            if order:
                side = "older" if order < 0 else "newer"
                issue("release_behind", f"The engine on port {item['port']} runs cadgen {item.get('release')}, {side} "
                                        f"than this cadgen {release}; they meet (protocol, document format, kernel line).",
                      f"Run `{runtime.INSTALL}` to bring the engine and every app's cadgen to the latest release.")
        elif item["selected"]:
            issue("engine_" + item["status"], "The selected engine is " + item["status"] + ".",
                  f"Use cadgen {release} on port {selected}. Start it explicitly if absent; stop only an engine you own.",
                  error=True)
        elif item["records"] and item["status"] in {"missing", "stale_endpoint"}:
            issue("stale_engine_record", f"A recorded engine on port {item['port']} does not answer.",
                  "A record is historical evidence; start an engine explicitly only when you need that port.")
    if python is not None and project_data["status"] == "ok":
        # The project meets the engine it builds with: the selected one where it named itself, else the
        # one this CLI starts (``runtime.refusal``; never the release).
        engine_item = next((item for item in engines if item["selected"] and type(item.get("protocol")) is int
                            and "native" in item), None)
        _project_findings(issue, project_data, item_identity(engine_item) if engine_item else ours, selected)
    provider_ports = {}
    for source in hosts["sources"]:
        if source.get("release") and source.get("port") and source.get("kind") != "cached_plugin":
            provider_ports.setdefault(source["port"], set()).add(source["release"])
    for port, releases in provider_ports.items():
        if len(releases) > 1:
            issue("provider_port_mismatch", f"Discoverable host configurations pin different releases on port {port}: "
                                            f"{', '.join(sorted(releases))}.",
                  "The newest one's engine serves the port once the others' are idle; run "
                  f"`{runtime.INSTALL}` to bring every app to the latest release.")
    exit_code = 3 if any(item["exit_code"] == 3 for item in issues) else 5 if any(
        item["severity"] == "error" for item in issues) else 0
    return {"schema": SCHEMA, "status": "error" if exit_code else "warning" if issues else "ok", "exit_code": exit_code,
            "current": current, "skill": skill_data, "project": project_data, "installations": installation_data,
            "selected_port": selected, "engines": engines, "engine_records": {"status": records_state, "records": records},
            "legacy_endpoints": {key: value for key, value in legacy.items() if key != "current_ports"},
            "hosts": hosts, "issues": issues}


def item_identity(item: dict) -> dict:
    """An engine's report (``engine``) as the rule reads a side (``runtime.side``)."""
    return {key: item.get(key) for key in ("protocol", "release", "writes", "reads", "native")}


def _engine_incompatible(item: dict, ours: dict) -> tuple[str, str]:
    """The selected engine that does not meet this CLI, in words naming what differs, and the remedy."""
    from cadgen.engine import client, runtime

    port, release = item["port"], item.get("release")
    if item.get("protocol") == "legacy-status":
        named = f"cadgen {item.get('installation') or release}'s engine" if release else "an older cadgen's engine"
        return (f"The selected engine on port {port} is {named}, which speaks an older protocol (the protocol "
                "differs).", f"Run `{client.stop_command(port)}` to stop it; a start retires an idle one on its own.")
    refused = runtime.refusal({**ours, "port": port}, item_identity(item), port=port)
    if refused is not None:
        return (f"The selected engine does not meet this cadgen {ours['release']} ({refused.what} differs): "
                f"{refused.words}.", _sentence(refused.remedy))
    why = "it serves another port" if item.get("reason") == "port" else "it refused this cadgen's handshake"
    return (f"The selected engine on port {port} (cadgen {release}) does not meet this cadgen {ours['release']}: {why}.",
            f"Run `{client.stop_command(port)}`, then start the engine again with this cadgen.")


def _project_findings(issue, project_data: dict, engine: dict, port: int | None) -> None:
    """The project Python's cadgen against the engine it builds with (``engine``): ``project_incompatible``
    where they do not meet (exit 3, naming what differs), ``release_behind`` where only their
    releases differ, with the nudge a build is given (``runtime.nudge``)."""
    from cadgen.engine import runtime

    theirs = project_data.get("release")
    meets = project_data.get("meets")
    if meets is None:
        issue("project_incompatible", f"The project Python's cadgen {theirs} does not say the protocol, document "
                                      "format and kernel line it meets an engine by: it predates them.",
              "Update cadgen in the project environment: uv pip install -U cadgen.", incompatible=True)
        return
    refused = runtime.refusal({**meets, "release": theirs}, engine, port=port)
    if refused is not None:
        issue("project_incompatible", f"The project Python's cadgen {theirs} does not meet the engine "
                                      f"({refused.what} differs): {refused.words}.",
              _sentence(refused.remedy), incompatible=True)
        return
    said = runtime.nudge(theirs, engine.get("release"))
    if said is not None:
        issue("release_behind", f"The project Python's cadgen {theirs} and the engine's {engine.get('release')} are "
                                "different releases that meet (protocol, document format, kernel line).",
              _sentence(said))


def human(data: dict) -> str:
    current = data["current"]
    lines = [f"cadgen {current['installation'] or current['release']} diagnostics ({data['status']})",
             f"  python {current['python_version']} ({current['python']})", f"  import {current['path']}",
             *([f"  meets {_meets_words(current['meets'])}"] if current.get("meets") else []),
             f"  skill {data['skill']['status']}" + (f" cadgen {data['skill']['release']}" if data['skill']['release'] else "")]
    project_data = data["project"]
    lines.append(f"  project {project_data['status']}" + (f" cadgen {project_data['release']} ({project_data.get('path', '')})"
                                                        if project_data.get("release") else "")
                 + (f", {_meets_words(project_data['meets'])}" if project_data.get("meets") else ""))
    for record in data["installations"]["records"]:
        lines.append(f"  installation {record.get('version', '?')}: {record['status']} ({record['path']})")
    for item in data["engines"]:
        lines.append(f"  engine port {item['port']}: {item['status']}" + (" (selected)" if item['selected'] else "")
                     + (f" ({item['reason']} differs)" if item.get("reason") in {"protocol", "format", "native"} else "")
                     + (f" cadgen {item['release']}" if item.get("release") else "")
                     + (f" installation {item['installation']}" if item.get("installation") else "")
                     + (f" ({item['protocol']})" if item.get("protocol") == "legacy-status" else "")
                     + (f", {_meets_words(item)}" if type(item.get("protocol")) is int and "native" in item else ""))
    for record in data.get("legacy_endpoints", {}).get("records", []):
        lines.append(f"  legacy endpoint {record['status']} ({record['path']})"
                     + (f" port {record['port']} cadgen {record['release']}" if record.get("port") else "")
                     + (f" installation {record['installation']}" if record.get("installation") else ""))
    for source in data["hosts"]["sources"]:
        if source["status"] != "missing":
            lines.append(f"  host {source['provider']} {source['kind']}: {source['status']}"
                         + (f" cadgen {source['release']} port {source.get('port')}" if source.get("release") else
                            f" installation {source['installation']} port {source.get('port')}" if source.get("installation") else "")
                         + f" ({source['path']})")
    lines.append("  coverage " + data["hosts"]["coverage"])
    for issue in data["issues"]:
        lines.extend([f"  {issue['severity']}: {issue['detail']}", "    " + issue["remedy"]])
    return "\n".join(lines) + "\n"


def _meets_words(meets: dict) -> str:
    """What a side meets another by, in words: ``protocol 4, writes xbf/10, reads xbf/8 to xbf/10,
    Darwin arm64 with OCP 8.0``."""
    words = [f"protocol {meets['protocol']}"]
    if meets.get("writes"):
        words.append(f"writes {meets['writes']}")
    if meets.get("reads"):
        reads = meets["reads"]
        words.append(f"reads {reads[0]}" + (f" to {reads[-1]}" if len(reads) > 1 else ""))
    native = meets.get("native")
    if isinstance(native, dict):
        words.append(f"{native['system']} {native['arch']} with " + (f"OCP {native['ocp_line']}" if native.get("ocp_line")
                                                                   else "no OCP"))
    return ", ".join(words)
