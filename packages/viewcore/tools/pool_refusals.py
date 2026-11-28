"""hosts/node/serve.mjs under input it must refuse: each is answered, and the server goes on to the next frame.

    python tools/pool_refusals.py [--node NODE] [--wasm dist/viewcore.wasm] [--big] FILE.xbf

Frames it cannot read, jobs it does not know, bytes that are no shape, files that are no .xbf, an ordinal a part has
not, and with ``--big`` a frame of 3 GiB let by as it comes; then a job that works, and ``close``. Exits 1 if one is
not refused in an answer of its own, or the server ends before its ``close``. Standard library only.
"""
import argparse
import json
import struct
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser()
parser.add_argument("file", type=Path)
parser.add_argument("--node", default="node")
parser.add_argument("--wasm", type=Path, default=HERE / "dist/viewcore.wasm")
parser.add_argument("--big", action="store_true")
given = parser.parse_args()
serve, xbf = str(HERE / "hosts/node/serve.mjs"), str(given.file.resolve())
p = subprocess.Popen([given.node, serve, str(given.wasm)], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
wrong = []


def raw(body):
    p.stdin.write(struct.pack(">Q", len(body)) + body)
    p.stdin.flush()


def frame(header, payloads=()):
    head = json.dumps({**header, "payloads": [len(x) for x in payloads]}).encode()
    raw(struct.pack(">I", len(head)) + head + b"".join(payloads))


def answer():
    (n,) = struct.unpack(">Q", p.stdout.read(8))
    body = p.stdout.read(n)
    (h,) = struct.unpack(">I", body[:4])
    return json.loads(body[4:4 + h]), body[4 + h:]


def refused(what):
    head, _rest = answer()
    print(f"{what:44s} -> {'refused: ' + head.get('error', '')[:100] if not head['ok'] else 'ANSWERED'}")
    if head["ok"]:
        wrong.append(what)


raw(b"\x00\x00"); refused("a frame shorter than a header length")
raw(struct.pack(">I", 999) + b"{}"); refused("a header longer than its frame")
raw(struct.pack(">I", 5) + b"{nope"); refused("a header that is no JSON")
raw(struct.pack(">I", 2) + b"[]"); refused("a header that is no object")
frame({"id": 1, "job": "mesh"}); refused("mesh with no payload")
head = json.dumps({"id": 2, "job": "mesh", "payloads": [50]}).encode()
raw(struct.pack(">I", len(head)) + head + b"x" * 7); refused("payload lengths that are not the frame's")
frame({"id": 3, "job": "nope"}); refused("a job it does not know")
frame({"id": 4, "job": "mesh"}, [b"not a shape at all"]); refused("bytes that are no shape")
frame({"id": 5, "job": "read_xbf", "path": xbf + ".gone"}); refused("a file that is not there")
frame({"id": 6, "job": "read_xbf", "path": serve}); refused("a file that is no .xbf")
frame({"id": 7, "job": "export", "path": xbf, "format": "dxf"}); refused("a format it does not write")
frame({"id": 8, "job": "read_xbf", "path": xbf})
head, rest = answer()
sizes = head["payloads"]
shape = rest[sizes[0]:sizes[0] + sizes[1]]
frame({"id": 9, "job": "fact", "key": "k", "method": "face", "args": [99999]}, [shape]); refused("a face the part has not")
frame({"id": 10, "job": "table", "key": "k", "unmeshed": ["x"]}, [shape]); refused("unmeshed that is no list of ordinals")
if given.big:
    big, chunk = 3 * 2**30, b"\0" * (64 * 2**20)
    p.stdin.write(struct.pack(">Q", big))
    for _ in range(big // len(chunk)):
        p.stdin.write(chunk)
    p.stdin.flush()
    refused("a frame of 3 GiB")
frame({"id": 11, "job": "fact", "key": "k", "method": "face", "args": [1]}, [shape])
head, rest = answer()
print(f"{'then a real face of the same part':44s} -> {'answered, ' + str(len(rest)) + ' bytes' if head['ok'] else 'REFUSED: ' + head.get('error', '')}")
if not head["ok"]:
    wrong.append("a real job after the refusals")
frame({"id": 12, "job": "close"})
closed, _ = answer()
p.stdin.close()
code = p.wait(30)
print(f"close -> ok={closed['ok']}, exit code {code}")
sys.exit(1 if wrong or code or not closed["ok"] else 0)
