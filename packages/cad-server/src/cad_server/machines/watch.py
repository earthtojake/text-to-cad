"""The machines the viewer watches: one reading thread per controller address, its last reading
numbered so a page waits for the next (``Watches.wait``), as it waits on a document's version.

A watch is started by a page (``POST /api/v1/machines``) and ends when a page stops it, or when no page
has asked after it for ``IDLE_SECONDS``: a closed tab leaves no thread reading a machine. Two pages
watching one address share its watch. Nothing a request does waits on the network: the thread
connects and reads, and a request only reads what it last found.
"""

from __future__ import annotations

import secrets
import threading
import time

from .reading import Address, Reading, parse_address

# How often a watch reads its controller: GRBL's documentation asks clients to keep status queries
# to about five a second, and MTConnect's and LinuxCNC's servers are well within it.
PERIOD = 0.2
# How long a watch waits before connecting again after it lost its controller.
RETRY = 2.0
# How long a watch keeps reading with no page asking after it.
IDLE_SECONDS = 30.0
# The longest one wait holds a request.
MAX_WAIT = 25.0
# How many machines one engine watches at once.
MAX_WATCHES = 8


def reader_for(address: Address):
    """The reader of ``address``'s protocol."""
    if address.protocol == "mtconnect":
        from .mtconnect import MtconnectReader
        return MtconnectReader(address)
    if address.protocol == "linuxcnc":
        from .linuxcnc import LinuxcncReader
        return LinuxcncReader(address)
    if address.protocol == "grbl":
        from .grbl import GrblReader
        return GrblReader(address)
    raise ValueError(f"no reader for {address.protocol}")


class Watch:
    """One controller, read on a thread of its own until stopped."""

    def __init__(self, ident: str, address: Address, reader, *, clock=time.monotonic, period=PERIOD, retry=RETRY,
                 idle=IDLE_SECONDS) -> None:
        self.id, self.address, self.reader = ident, address, reader
        self.clock, self.period, self.retry, self.idle = clock, period, retry, idle
        self.changed = threading.Condition()
        self.version = 0
        self.connected = False
        self.reading: Reading | None = None
        self.error: str | None = None
        self.asked = clock()
        self.stopping = threading.Event()
        self.thread = threading.Thread(target=self._run, name=f"cad-machine-{ident}", daemon=True)

    def start(self) -> None:
        self.thread.start()

    def stop(self) -> None:
        self.stopping.set()
        with self.changed:
            self.changed.notify_all()

    def state(self) -> dict:
        with self.changed:
            return {"id": self.id, "address": str(self.address), "protocol": self.address.protocol,
                    "version": self.version, "connected": self.connected, "error": self.error,
                    "reading": self.reading.as_json() if self.reading else None}

    def wait(self, after: int, seconds: float) -> dict:
        """Its state once its version is past ``after``, or after ``seconds``, whichever is first."""
        self.asked = self.clock()
        deadline = time.monotonic() + max(0.0, min(seconds, MAX_WAIT))
        with self.changed:
            while self.version <= after and not self.stopping.is_set():
                left = deadline - time.monotonic()
                if left <= 0:
                    break
                self.changed.wait(left)
        self.asked = self.clock()
        return self.state()

    def _publish(self, *, connected: bool, reading: Reading | None, error: str | None) -> None:
        with self.changed:
            if (connected, reading, error) == (self.connected, self.reading, self.error):
                return
            self.connected, self.reading, self.error = connected, reading, error
            self.version += 1
            self.changed.notify_all()

    def _run(self) -> None:
        while not self.stopping.is_set():
            try:
                self.reader.open()
                self._publish(connected=True, reading=self.reading, error=None)
                while not self.stopping.is_set():
                    if self.clock() - self.asked > self.idle:
                        self.stop()  # no page has asked after it: nothing is left to read for
                        break
                    reading = self.reader.read()
                    if reading is not None:
                        self._publish(connected=True, reading=reading, error=None)
                    self.stopping.wait(self.period)
            except Exception as error:  # noqa: BLE001 -- what went wrong is the page's to show; the watch tries again
                self._publish(connected=False, reading=self.reading, error=str(error) or type(error).__name__)
            finally:
                try:
                    self.reader.close()
                except Exception:  # noqa: BLE001 -- a socket that will not close is gone anyway
                    pass
            if self.clock() - self.asked > self.idle:
                self.stop()
            self.stopping.wait(self.retry)


class Watches:
    """Every machine the engine watches, by id."""

    def __init__(self, *, reader_for=reader_for, clock=time.monotonic, idle=IDLE_SECONDS, **watch_options) -> None:
        self.reader_for, self.clock, self.idle, self.watch_options = reader_for, clock, idle, watch_options
        self.lock = threading.Lock()
        self.watches: dict[str, Watch] = {}

    def start(self, text: str) -> dict:
        """The watch of the address ``text`` names, started if no page watches it yet."""
        address = parse_address(text)
        with self.lock:
            self._reap()
            for watch in self.watches.values():
                if str(watch.address) == str(address):
                    watch.asked = self.clock()
                    return watch.state()
            if len(self.watches) >= MAX_WATCHES:
                raise OverflowError(f"this engine watches {MAX_WATCHES} machines already: stop one first")
            watch = Watch(secrets.token_hex(8), address, self.reader_for(address), clock=self.clock, idle=self.idle,
                          **self.watch_options)
            self.watches[watch.id] = watch
        watch.start()
        return watch.state()

    def get(self, ident: str) -> Watch | None:
        with self.lock:
            self._reap()
            return self.watches.get(ident)

    def stop(self, ident: str) -> bool:
        with self.lock:
            watch = self.watches.pop(ident, None)
        if watch is None:
            return False
        watch.stop()
        return True

    def close(self) -> None:
        with self.lock:
            watches, self.watches = list(self.watches.values()), {}
        for watch in watches:
            watch.stop()

    def _reap(self) -> None:
        now = self.clock()
        for ident, watch in list(self.watches.items()):
            if watch.stopping.is_set() or now - watch.asked > self.idle:
                del self.watches[ident]
                watch.stop()
