"""``cad mcp``: the host's stdio transport, forwarding JSON-RPC to this release's CAD server.

What it does, in order: start this release's server once, as it starts, exactly as ``cad server start`` does
(``start_server``, on a thread of its own, ``Holder``), and hold it while the host runs; pass the host's requests on to
the server's HTTP endpoint, as its door names it at each request (``call``), and the server's answers back
(``Proxy``). It installs nothing, and starts no server after its own start: a server stopped later (``cad server
stop``) stays stopped. Several started at once end with one server (``client.start``: the daemon's lock).

Only connection metadata lives here. Tools, views, pages and document state belong to the server. Host
capability corrections are made at this boundary: the development switch (``CAD_MCP_PRESENTATION``), and
which host launched this process, read from its parent processes (``host.launcher``), which only this
process can see. So is the one act a text host's ``cad_show`` asks of the person's machine, opening their
browser: made here, in the environment the host gave this process, never in the server's
(``browser.deliver``), and its outcome told to the server before the host has the answer
(``browser.OPENED``). Nothing of it outlives the request it serves.

**Answered here** (``Proxy.handle``), never left waiting, and nothing reaching a server:

- ``ping``: an empty result, at once (it is answered on the reader, which nothing may hold).
- While the start runs (seconds; a server of another release is stopped first, ``client.STOP_SECONDS`` at most):
  ``initialize`` waits ``INITIALIZE_SECONDS`` for it, well inside the 30 seconds Codex gives a server to start, then
  is greeted here (``_greeting``), and the server's session opened at the host's first request once the start is done.
  Every other request waits ``READY_SECONDS``, then: ``tools/list``, ``resources/list`` and
  ``resources/templates/list`` an empty list, and ``notifications/tools/list_changed`` (``resources/list_changed``)
  sent once the start is done, so the app asks again; ``tools/call`` a result marked ``isError`` saying the server is
  starting; any other a JSON-RPC error (``UNAVAILABLE``) saying so.
- Where no server of this release or a newer one answers (the start failed, the server was stopped since, an older
  release's runs, one that takes the request and never answers it): ``tools/call`` a result marked ``isError`` carrying
  cad's one line
  (``client.NotRunning``, ``client.OtherRelease``, ``client.Unanswered``), which the agent reads and relays; any other
  request a JSON-RPC error carrying it. The host's ``initialize`` is answered within ``ANSWER_SECONDS`` in every case:
  greeted here, as while the start runs, where the server does not answer in time.
"""
from __future__ import annotations

import copy
import http.client
import json
import logging
import os
import secrets
import signal
import sys
import threading
import time
from urllib.parse import urlsplit

from cad.engine import client
from cad.engine.previous import version
from cad_mcp.browser import OPENED, deliver, transport_browser
from cad_mcp.host import family, launcher
from cad_mcp.protocol import Connection, RequestContext, RpcError, claim_stdin, claim_stdout

LOG = logging.getLogger("cad_mcp")
# How long the host's initialize waits for this transport's start of the server, and every other request: within
# the 30 seconds Codex gives an MCP server to start, past which the request is answered here. And how long the
# initialize may take in all, its session's opening on the server with it (``ANSWER_SECONDS``), and the door's naming
# of the endpoint for any request (``DOOR_SECONDS``): a server that takes a request and never answers ends it with
# cad's line, never hangs it. Neither bounds a request the server's endpoint serves (``call``).
INITIALIZE_SECONDS = 20.0
READY_SECONDS = 5.0
ANSWER_SECONDS = 25.0
DOOR_SECONDS = 20.0
STARTING = f"the {client.COMMAND} server is starting: try again shortly"
# The JSON-RPC error a request answered here carries (the server's own -32000, an implementation's).
UNAVAILABLE = -32000
# The lists an app asks for, what each answer holds them under, and the notification that it changed.
LISTS = {"tools/list": ("tools", "notifications/tools/list_changed"),
         "resources/list": ("resources", "notifications/resources/list_changed"),
         "resources/templates/list": ("resourceTemplates", "notifications/resources/list_changed")}
# The presentations the development switch forces on any client (``CAD_MCP_PRESENTATION``; the server's
# ``host.presentation``).
PRESENTATIONS = ("inline", "tabs", "text")


def start_server() -> str:
    """THE ONE PLACE ``cad mcp`` decides what a server of another release means, so a later release changes the rule
    here alone. At its own start, exactly what ``cad server start`` does (``client.start``: a server of an older
    release, or of 0.11.10 and earlier, told to stop, its work cut short, and this release's started; one of this
    release or a newer one joined). After it, the server running is reached where it is this release's or newer
    (``client.AT_LEAST``: cad updated itself under this transport): a request that finds an older one is answered
    with cad's one line saying both (``client.OtherRelease``), as one that finds none is (``client.NotRunning``), and
    nothing is started again. What the start did, in one line; ``ConnectionError`` in one line where it could not."""
    client.AT_LEAST = version()
    return client.start()


def call(method, path, body=b"", headers=None, timeout=None):
    """One HTTP request to the MCP endpoint of the server running now, as its door names it at this very call (``op:
    http``, ``DOOR_SECONDS`` at most): a loopback port is anyone's once the server has let it go, and every call
    carries the user's page token, so no endpoint is kept from one call to the next. ``(status, headers, body)``;
    ``ConnectionError`` in cad's one line where no server of this release runs (``start_server``) or its door does
    not answer (``client.Unanswered``). It never starts one. ``timeout``: the seconds the whole call may take (the
    host's initialize, ``Proxy.handle``); None, the door's bound and then as long as the endpoint takes."""
    deadline = None if timeout is None else time.monotonic() + timeout
    endpoint = client.request({"op": "http"}, timeout=DOOR_SECONDS if timeout is None else min(DOOR_SECONDS, timeout))
    if "failed" in endpoint:
        raise ConnectionError(endpoint["failed"])
    parsed = urlsplit(endpoint["url"])
    left = 600 if deadline is None else max(0.1, deadline - time.monotonic())
    connection = http.client.HTTPConnection(parsed.hostname, parsed.port, timeout=left)
    try:
        connection.request(method, path, body=body,
                           headers={**(headers or {}), "Authorization": "Bearer " + endpoint["token"]})
        response = connection.getresponse()
        return response.status, dict(response.getheaders()), response.read()
    finally:
        connection.close()


def initialize_params(params, launcher=None, holder=None, app=None):
    """The host's initialize as the server is sent it: with ``presentation``, the development switch
    ``CAD_MCP_PRESENTATION`` (``inline``, ``tabs`` or ``text``) where it is set, which the server serves whatever
    the client is; ``launcher``, the host that started this process (``host.launcher``), for the server to weigh
    (its ``host.presentation``); ``holder``, the name of this process's hold (``Holder``), whose end ends the
    session; ``app``, the capability the session hands its views (``Proxy.app``); and ``browser``: that this
    process opens the browser a text host's ``cad_show`` asks for (``browser.deliver``), and whether it can here."""
    params = copy.deepcopy(params)
    told = str(os.environ.get("CAD_MCP_PRESENTATION") or "").strip()
    params.setdefault("_meta", {})["dev.texttocad/transport"] = {
        "appDir": os.environ.get("CAD_MCP_APP_DIR", ""), "cwd": os.getcwd(), "launcher": launcher,
        "browser": transport_browser(),
        **({"presentation": told} if told in PRESENTATIONS else {}),
        **({"holder": holder} if holder else {}), **({"app": app} if app else {}),
    }
    return params


class Holder:
    """This transport's start of the server and its hold on it. As the transport starts: this release's server
    started, once (``start_server``; ``started`` set when that is done, however it went), then held while the host
    runs, so a shell the host runs in a sandbox that cannot start a server finds one, and the sessions this process
    opens (under ``ident``) end when it goes. A server that goes while held (``cad server stop``, a crash) is held
    again at the host's next request where one of this release runs, and never started: a stop is obeyed."""

    def __init__(self, host=lambda: None):
        self.host = host  # the host this transport serves, said with the hold (``host.family``)
        self.ident = secrets.token_urlsafe(18)
        self.started = threading.Event()
        self.wanted = threading.Event()
        self.holding = False
        self.thread = threading.Thread(target=self._run, name="cad-mcp-hold", daemon=True)

    def start(self):
        self.thread.start()

    def want(self):
        if not self.holding:
            self.wanted.set()

    def _run(self):
        try:
            LOG.info("%s", start_server())
        except Exception as error:  # noqa: BLE001 - said here, and to each request that needs the server (``Proxy``)
            LOG.info("%s", error)
        finally:
            self.started.set()
        while True:
            try:
                connection = client.hold(host=self.host, holder=self.ident)
            except Exception as error:  # noqa: BLE001 - none runs, or another release's: tried at the next request
                LOG.info("could not hold the %s server: %s", client.COMMAND, error)
            else:
                self.holding = True
                self.wanted.clear()  # the requests made while it was taken are served by this hold
                try:
                    with connection:
                        while connection.reader.read(4096):
                            pass  # until the server goes
                except OSError:
                    pass
                finally:
                    self.holding = False
                LOG.info("the %s server this transport held has stopped", client.COMMAND)
            self.wanted.wait()
            self.wanted.clear()


class Proxy:
    """One host connection's server session. The host initializes once, but the server's session can end
    under it (the server restarted, or the session's idle hour passed): the transport then opens a new one
    with the host's own initialize and sends the request again, so the host never has to reconnect. Only a
    request the server never took is sent again: one it refused for an unknown session, or one whose
    connection was refused. Each session it opens is given the same app capability (``app``), so the views
    the host shows keep reaching CAD through the new one. ``call`` sends one HTTP request (the module's
    ``call``); ``holder`` is the transport's start and hold (``Holder``): with none, the server is reached as
    it runs and nothing waits for a start."""

    def __init__(self, call=call, holder=None, launcher=lambda: None, opener=None):
        self.call = call
        self.opener = opener  # what opens a page's redirect file: ``webbrowser.open``, in this environment
        self.holder = holder
        self.launcher = launcher  # the host that started this process, read once (``serve``)
        self.session = None
        self.protocol = None
        self.initialize = None  # the host's initialize, as the server is sent it
        self.initialized = False  # whether the host said notifications/initialized
        self.app = secrets.token_urlsafe(32)
        self.lock = threading.Lock()
        self.tell = None  # what sends the host a notification (``protocol.Connection.notify``), once serving
        self.offered = False  # whether the tools the server offers were logged (once: ``_declared``'s pair)
        self.unlisted = set()  # the list-changed notifications owed once the start is done

    def _ready(self, wait):
        """Whether this transport's start of the server is done (``Holder.started``), waited for ``wait`` seconds at
        most."""
        return self.holder is None or self.holder.started.wait(wait)

    def _send(self, message, session, timeout=None):
        if self.holder is not None:
            self.holder.want()
        headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
        if session:
            headers["Mcp-Session-Id"], headers["MCP-Protocol-Version"] = session
        bound = {} if timeout is None else {"timeout": timeout}
        return self.call("POST", "/mcp", json.dumps(message).encode("utf-8"), headers, **bound)

    def _open(self, request_id, params, timeout=None):
        status, reply_headers, data = self._send({"jsonrpc": "2.0", "id": request_id, "method": "initialize",
                                                  "params": params}, None, timeout)
        answer = self._answer(status, data)
        headers = {name.lower(): value for name, value in reply_headers.items()}
        session = (headers["mcp-session-id"], answer["result"]["protocolVersion"])
        with self.lock:
            self.session, self.protocol = session
        return answer["result"], session

    def _reopen(self, stale):
        """A new server session for the host's, once per ended one however many requests find it ended."""
        with self.lock:
            if self.initialize is None:
                raise RpcError(UNAVAILABLE, "The engine session ended before this server was initialized.")
            current = (self.session, self.protocol) if self.session else None
            if current is not None and current != stale:
                return current  # another request opened it already
            params, initialized = self.initialize, self.initialized
        LOG.info("opening a session on the %s server", client.COMMAND)
        _result, session = self._open("cadgen-reopen", params)
        if initialized:
            self._send({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}}, session)
        return session

    @staticmethod
    def _answer(status, data):
        if status not in (200, 202):
            raise RpcError(UNAVAILABLE, f"Engine MCP endpoint returned HTTP {status}.")
        if status == 202:
            return {}
        answer = json.loads(data)
        if "error" in answer:
            error = answer["error"]
            raise RpcError(error["code"], error["message"], error.get("data"))
        return answer

    def _post(self, message):
        with self.lock:
            session = (self.session, self.protocol) if self.session else None
            pending = session is None and self.initialize is not None
        if pending:
            # The host's initialize was answered here (``handle``): the server's session is opened now, with it.
            session = self._reopen(None)
        for attempt in (1, 2):
            try:
                status, _headers, data = self._send(message, session)
            except ConnectionRefusedError:
                # The server the door named went before its endpoint was reached: the request reached nothing.
                if attempt == 2 or session is None:
                    raise
                status = 404
            if status != 404 or session is None or attempt == 2:
                break
            session = self._reopen(session)
        if status == 404:
            raise RpcError(UNAVAILABLE, "The engine session ended and a new one could not be opened.")
        answer = self._answer(status, data)
        return answer.get("result", {}) if answer else {}

    def handle(self, method, params, context: RequestContext):
        if method == "ping":
            return {}
        if method == "initialize":
            arrived = time.monotonic()
            launched = self.launcher()
            _declared(params, launched)
            params = initialize_params(params, launched, self.holder.ident if self.holder is not None else None,
                                       self.app)
            with self.lock:
                self.initialize = params  # the session opened with it later, where it cannot be now
            if not self._ready(max(0.0, INITIALIZE_SECONDS - (time.monotonic() - arrived))):
                LOG.info("the %s server is still starting: the session opens at the app's next request", client.COMMAND)
                return _greeting(params)
            try:
                return self._open(context.request_id, params,
                                  timeout=max(1.0, ANSWER_SECONDS - (time.monotonic() - arrived)))[0]
            except (client.Unanswered, TimeoutError):
                LOG.info("the %s server did not answer in time: the session opens at the app's next request",
                         client.COMMAND)
                return _greeting(params)
            except ConnectionError as error:
                raise RpcError(UNAVAILABLE, str(error)) from None
        if not self._ready(READY_SECONDS):
            return self._local(method, STARTING, starting=True)
        try:
            result = self._post({"jsonrpc": "2.0", "id": context.request_id, "method": method, "params": params})
        except ConnectionError as error:
            return self._local(method, str(error))
        if method == "tools/list" and not self.offered:
            self.offered = True
            names = [tool.get("name") for tool in result.get("tools", []) if isinstance(tool, dict)]
            LOG.info("the server offers this app %s", ", ".join(map(str, names)) if names else "no tools")
        # A text host's cad_show: the page the server names is opened here, never by the server, and the
        # server told whether it opened before the host is answered.
        return deliver(result, self.opener, self._tell) if method == "tools/call" else result

    def _local(self, method, line, *, starting=False):
        """Request ``method`` answered here with ``line``, where the server cannot be reached: still ``starting``, or
        not running (see the module's "Answered here")."""
        if method == "tools/call":
            return {"content": [{"type": "text", "text": line}], "isError": True}
        if starting and method in LISTS:
            key, changed = LISTS[method]
            self._owe(changed)
            return {key: []}
        raise RpcError(UNAVAILABLE, line)

    def _owe(self, changed):
        """List-changed notification ``changed`` sent once the start is done, so the app asks again for a list
        answered empty while it ran: by one thread, which sends every one owed by then."""
        with self.lock:
            first = not self.unlisted
            self.unlisted.add(changed)
        if first:
            threading.Thread(target=self._announce, name="cad-mcp-announce", daemon=True).start()

    def _announce(self):
        self.holder.started.wait()  # ``client.start`` is bounded
        with self.lock:
            owed, self.unlisted = sorted(self.unlisted), set()
        for changed in owed:
            if self.tell is not None:
                self.tell(changed, {})

    def _tell(self, url, opened):
        """The server told, on this session, whether the page it asked this process to open opened
        (``browser.OPENED``): it counts the page as open in the person's browser only once told it did."""
        try:
            self._post({"jsonrpc": "2.0", "method": OPENED, "params": {"url": url, "opened": opened}})
        except Exception as error:  # noqa: BLE001 - the server's next show of the page opens it again
            LOG.info("could not tell the server whether the page opened: %s", error)

    def notify(self, method, params):
        if method == "notifications/initialized":
            with self.lock:
                self.initialized = True
                if self.session is None:
                    return  # the server's session is not open yet: it is told as it opens (``_reopen``)
        if not self._ready(0.0):
            return  # nothing reaches a server before the start is done (the module's "Answered here")
        try:
            self._post({"jsonrpc": "2.0", "method": method, "params": params})
        except (ConnectionError, RpcError) as error:
            LOG.info("could not pass %s on: %s", method, error)

    def close(self):
        with self.lock:
            ident = self.session
        if ident:
            # The session's end, told to the server that holds it, where one runs: never a server started to hear it.
            try:
                self.call("DELETE", "/mcp", headers={"Mcp-Session-Id": ident})
            except OSError:
                pass


def _declared(params, launched):
    """What the app said of itself at ``initialize``, logged to this process's stderr (the app's log of its MCP
    servers): its client's name and version, the extensions it declares and the program that launched this process
    (which, for a Codex, decides whether the server offers it tools). The server's answer is logged with the first
    ``tools/list``."""
    params = params if isinstance(params, dict) else {}
    client_info = params.get("clientInfo") if isinstance(params.get("clientInfo"), dict) else {}
    offered = params.get("capabilities") if isinstance(params.get("capabilities"), dict) else {}
    extensions = offered.get("extensions") if isinstance(offered.get("extensions"), dict) else {}
    said = [f"{name} {json.dumps(value, sort_keys=True)}" for name, value in sorted(extensions.items())]
    LOG.info("%s %s declares %s; launched by %s", client_info.get("name", "an app"), client_info.get("version", ""),
             "; ".join(said) or "no extensions",
             (launched or {}).get("host") if isinstance(launched, dict) else "an unknown program")


def _greeting(params):
    """The host's initialize answered here, while this transport's start runs (``Proxy.handle``): the protocol it
    asked for, the capabilities every session of the server has, with lists that change (a list asked for before the
    start is done is answered empty, and changes once it is: ``Proxy._owe``), and the server's name. The server's own
    answer -- its instructions among them -- is its session's, opened at the first request once the start is done."""
    asked = params.get("protocolVersion") if isinstance(params, dict) else None
    return {"protocolVersion": asked if isinstance(asked, str) and asked else "2025-06-18",
            "capabilities": {"tools": {"listChanged": True}, "resources": {"listChanged": True}},
            "serverInfo": {"name": "cad", "title": "CAD", "version": version()}}


def _leave(number, _frame):
    raise SystemExit(128 + number)


def serve():
    """Serve the host on standard input and output until it closes them, or ends this process: this release's
    server started first, on a thread of its own (``Holder``), which every request to the server waits for, the
    host's initialize ``INITIALIZE_SECONDS`` at most."""
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="cad mcp: %(message)s")
    output = claim_stdout()
    requests = claim_stdin()
    # Which host started this process, read from its parents while the host starts to greet it.
    found = {}
    reading = threading.Thread(target=lambda: found.update(host=launcher()), name="cad-mcp-host", daemon=True)
    reading.start()

    def launched():
        reading.join(5)
        return found.get("host")

    # The server started and held from the start, not from the first card; the hold names the host once it is read.
    holder = Holder(host=lambda: family(launched()))
    holder.start()
    proxy = Proxy(holder=holder, launcher=launched)
    connection = Connection(requests, output, proxy.handle, workers=64, notification=proxy.notify)
    proxy.tell = connection.notify
    # A host that ends this process with a signal rather than by closing its input (or both, at once): it
    # leaves as at the input's end, its session ended (``proxy.close``) before it exits.
    for name in ("SIGTERM", "SIGHUP"):
        if hasattr(signal, name):
            signal.signal(getattr(signal, name), _leave)
    try:
        connection.serve()
    finally:
        proxy.close()
        # A start under way is finished before this process leaves, never left half done (a server of another
        # release stopped, and this release's not yet started): it is bounded.
        holder.started.wait(client.STOP_SECONDS + client.START_SECONDS)
    return 0


USAGE = ("usage: {prog}\n\nServe CAD to the agent app that started this process, over MCP on standard input and "
         "output: this release's cad server started first, as `cad server start` starts it, and every request passed "
         "on to it. The app starts it; there is nothing to configure.\n")


def main(argv=None, prog="cad mcp"):
    """``cad mcp`` (and ``cad-mcp``, its name in releases before): serve CAD to the app that started this process.
    ``--startup-timeout SECONDS``, which configs of releases before give, is taken and ignored."""
    args = list(sys.argv[1:] if argv is None else argv)
    if args[:1] in (["-h"], ["--help"]):
        sys.stdout.write(USAGE.format(prog=prog))
        return 0
    while args:
        word = args.pop(0)
        if word == "--startup-timeout" and args:
            args.pop(0)
        elif not word.startswith("--startup-timeout="):
            sys.stderr.write(f"{prog}: unrecognized arguments: {word}\n")
            return 2
    return serve()
