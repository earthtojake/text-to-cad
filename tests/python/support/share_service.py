"""The share service on this computer, for a test: the real Worker over Node's http (``apps/share/serve.mjs``), its
shares in memory, on a port of its own, stopped with the test; and a share's manifest unsealed as the hosted viewer
unseals it (``cad-share/2``: AES-256-GCM under the key HKDF-SHA256 derives from the share's id), by Node's Web
Crypto, since Python's standard library has no AES.

``start`` answers the service's origin once it says it (the one line ``serve.mjs`` prints when it listens); its
static assets are an empty folder of the test's, as no page is opened. ``view`` reads a share's view as the page does,
each file unsealed and inflated.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import threading
from collections.abc import Callable
from typing import Any

from tests.python.support.paths import repo_path

__all__ = ["manifest", "start", "view"]

SERVE = repo_path("apps", "share", "serve.mjs")
# How long the service may take to say it listens, and an unsealing to answer, in seconds.
STARTED_SECONDS = 60.0
UNSEALED_SECONDS = 60.0

# A share's manifest as the viewer reads it: fetched from the service, opened with the key its id derives.
_UNSEAL = """
const [origin, id] = process.argv.slice(1);
const text = new TextEncoder();
const input = await crypto.subtle.importKey('raw', text.encode(id), 'HKDF', false, ['deriveBits']);
const bits = await crypto.subtle.deriveBits({ name: 'HKDF', hash: 'SHA-256', salt: text.encode('cad-share/2'),
  info: text.encode('key') }, input, 256);
const key = await crypto.subtle.importKey('raw', bits, 'AES-GCM', false, ['decrypt']);
const answer = await fetch(`${origin}/v1/shares/${id}`, { cache: 'no-store' });
if (!answer.ok) { console.error(`the service answered ${answer.status}`); process.exit(1); }
const sealed = new Uint8Array(await answer.arrayBuffer());
const plain = await crypto.subtle.decrypt({ name: 'AES-GCM', iv: sealed.subarray(0, 12),
  additionalData: text.encode('cad-share/2 manifest'), tagLength: 128 }, key, sealed.subarray(12));
process.stdout.write(new TextDecoder().decode(plain));
"""


def start(cleanup: Callable[..., Any]) -> str:
    """The share service started on a free port, until ``cleanup`` (a test's or a class's ``addCleanup``) stops it:
    its origin, ``http://127.0.0.1:<port>``, once it listens."""
    node = shutil.which("node")
    if node is None:
        raise RuntimeError("the share service runs on Node.js, and no node is on the PATH")
    assets = tempfile.mkdtemp(prefix="share-assets-")
    cleanup(shutil.rmtree, assets, True)
    process = subprocess.Popen([node, str(SERVE), "--port", "0", "--assets", assets], stdin=subprocess.DEVNULL,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8")

    def stop() -> None:
        process.terminate()
        try:
            process.communicate(timeout=30)
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate()

    cleanup(stop)
    said: list[str] = []
    reader = threading.Thread(target=lambda: said.append(process.stdout.readline()), daemon=True)
    reader.start()
    reader.join(STARTED_SECONDS)
    origin = said[0].strip() if said else ""
    if not origin.startswith("http://"):
        stop()
        raise RuntimeError(f"the share service did not start: {origin or process.stderr.read()}")
    return origin


# A share's view as the viewer reads it: its manifest opened, then each pack its view names, each file's ranges joined
# and inflated; every file by its path, its bytes in base64.
_VIEW = _UNSEAL.replace("process.stdout.write(new TextDecoder().decode(plain));", """
const manifest = JSON.parse(new TextDecoder().decode(plain));
const { gunzipSync } = await import('node:zlib');
const packs = new Map();
const view = {};
for (const [path, entry] of Object.entries(manifest.view)) {
  const parts = [];
  for (const [pack, offset, length] of entry.at) {
    if (!packs.has(pack)) {
      const got = new Uint8Array(await (await fetch(`${origin}/v1/shares/${id}/packs/${pack}`)).arrayBuffer());
      packs.set(pack, new Uint8Array(await crypto.subtle.decrypt({ name: 'AES-GCM', iv: got.subarray(0, 12),
        additionalData: text.encode(`cad-share/2 pack ${pack}`), tagLength: 128 }, key, got.subarray(12))));
    }
    parts.push(packs.get(pack).subarray(offset, offset + length));
  }
  view[path] = gunzipSync(Buffer.concat(parts)).toString('base64');
}
process.stdout.write(JSON.stringify(view));
""")


def _node(script: str, origin: str, ident: str) -> str:
    done = subprocess.run([shutil.which("node") or "node", "--input-type=module", "-e", script, origin, ident],
                          stdin=subprocess.DEVNULL, capture_output=True, text=True, encoding="utf-8",
                          timeout=UNSEALED_SECONDS, check=False)
    if done.returncode != 0:
        raise RuntimeError(f"the share did not open: {done.stderr.strip()}")
    return done.stdout


def view(origin: str, ident: str) -> dict[str, bytes]:
    """The view of the share ``ident`` the service at ``origin`` holds, as a page reads it: each file by its path."""
    import base64

    return {path: base64.b64decode(data) for path, data in json.loads(_node(_VIEW, origin, ident)).items()}


def manifest(origin: str, ident: str) -> dict[str, Any]:
    """The manifest of the share ``ident`` the service at ``origin`` holds, unsealed: its name, entry and made, and its
    two maps of files, the view's and the files that made it."""
    return json.loads(_node(_UNSEAL, origin, ident))
