#!/usr/bin/env node
// python.mjs: the WebAssembly kernel as a Python the engine can start (prototype). It takes the part of CPython's
// command line the engine's kernel processes are started with -- `python [-X opt] [-P] [-B] [-u] [-I] -m MODULE
// [ARGS]`, `-c CODE [ARGS]`, `SCRIPT [ARGS]` -- and runs it in Pyodide (CPython compiled to WebAssembly) with the
// CAD kernel's binding, on a kernel folder make.mjs made. The program sees the computer as a native Python would:
//
//   - the real filesystem at its own paths (every top-level folder mounted where it is), so a script, its `.xbf`,
//     the engine's folders and cad's own source are the files the engine names;
//   - the real standard streams, as bytes: the engine's worker protocol (frames on the pipe) passes untouched;
//   - the real environment, working folder, process id and file times (bootstrap.py puts right what the platform
//     rounds or invents);
//   - `sys.path` as CPython makes it: the script's folder (unless -P), PYTHONPATH (unless -E or -I), then the
//     kernel folder's site-packages, its `.pth` files read and `sitecustomize` imported (unless -S).
//
//   - sockets a program opens to a port or a path of this computer or another (the engine's own client is one):
//     the host's, since the platform has none here. Nothing listens.
//
// What it cannot be: a Python with threads or child processes. A program that starts one fails there, as on any
// Pyodide.
//
// The kernel folder is named by CAD_KERNEL_HOME, or is the folder two above this file's launcher (make.mjs writes
// `KERNEL/bin/python`, which sets it).
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { Worker } from "node:worker_threads";

const HERE = path.dirname(fileURLToPath(import.meta.url));
// Node 22's V8 keeps a copy of the kernel's function table per loaded library: 4.3 GB for this kernel, against
// 2 GB from Node 24 on.
const NODE_FLOOR = 24;

function refuse(text, code = 2) {
  fs.writeSync(2, `python (the WebAssembly kernel): ${text}\n`);
  process.exit(code);
}

const major = Number(process.versions.node.split(".")[0]);
if (major < NODE_FLOOR && process.env.CAD_KERNEL_ANY_NODE !== "1") {
  refuse(`Node ${process.versions.node} holds over 4 GB for this kernel; run it with Node ${NODE_FLOOR} or later `
    + "(the kernel folder's bin/python names the Node it runs: make it again with a newer one)");
}

const home = process.env.CAD_KERNEL_HOME;
if (!home || !fs.existsSync(path.join(home, "kernel.json"))) {
  refuse("CAD_KERNEL_HOME names no kernel folder (make one: node make.mjs PACKAGES_DIR KERNEL_DIR)");
}
const made = JSON.parse(fs.readFileSync(path.join(home, "kernel.json"), "utf8"));

// The command line, as CPython reads it.
const args = process.argv.slice(2);
const run = { safe: false, isolated: false, site: true, unbuffered: false, xoptions: [], kind: null, target: null,
  argv: [] };
while (args.length) {
  const arg = args.shift();
  if (arg === "-X") { run.xoptions.push(args.shift() ?? ""); continue; }
  if (arg.startsWith("-X") && arg.length > 2) { run.xoptions.push(arg.slice(2)); continue; }
  if (arg === "-m" || arg === "-c") {
    run.kind = arg === "-m" ? "module" : "code";
    run.target = args.shift();
    if (run.target === undefined) refuse(`argument expected for the ${arg} option`);
    run.argv = args.splice(0);
    break;
  }
  if (arg === "-") { run.kind = "stdin"; run.argv = args.splice(0); break; }
  if (arg.startsWith("-") && arg.length > 1) {
    // Single-letter options, which may be written together (-BP).
    for (const letter of arg.slice(1)) {
      if (letter === "P") run.safe = true;
      else if (letter === "I") run.safe = run.isolated = true;
      else if (letter === "E") run.isolated = true;
      else if (letter === "S") run.site = false;
      else if (letter === "u") run.unbuffered = true;
      else if (!"BsqOdvb".includes(letter)) refuse(`unknown option -${letter}`);
    }
    continue;
  }
  run.kind = "script";
  run.target = arg;
  run.argv = args.splice(0);
  break;
}
if (run.kind === null) refuse("no program: this Python runs -m MODULE, -c CODE or a SCRIPT, never a prompt");

const { loadPyodide } = await import(pathToFileURL(path.join(home, "pyodide", "pyodide.mjs")).href);
const pyodide = await loadPyodide({
  indexURL: path.join(home, "pyodide") + path.sep,
  // The program's environment is the process's own.
  env: { ...process.env, HOME: process.env.HOME || "/" },
});

// The standard streams as bytes, read and written where the process's are. A read waits for input as a native
// read does (the engine's worker waits on its pipe between requests).
function readInput(buffer) {
  for (;;) {
    try {
      return fs.readSync(0, buffer);
    } catch (error) {
      if (error.code === "EOF") return 0;
      if (error.code !== "EAGAIN") throw error;
      Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, 5);  // a pipe left non-blocking: ask again
    }
  }
}
function writer(fd) {
  return (buffer) => {
    let sent = 0;
    while (sent < buffer.length) {
      try {
        sent += fs.writeSync(fd, buffer, sent);
      } catch (error) {
        if (error.code !== "EAGAIN") throw error;
        Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, 2);
      }
    }
    return buffer.length;
  };
}
pyodide.setStdin({ read: readInput });
pyodide.setStdout({ write: writer(1) });
pyodide.setStderr({ write: writer(2) });

// The real filesystem at its own paths. Pyodide's own folders stay its own: /lib holds its standard library, /dev
// its devices. On Windows nothing is mounted (its paths are not this platform's): the engine does not offer the
// WebAssembly kernel there yet.
const FS = pyodide.FS;
const KEPT = new Set(["dev", "lib", "sys"]);
if (process.platform !== "win32") {
  for (const name of fs.readdirSync("/")) {
    if (KEPT.has(name)) continue;
    try {
      if (!fs.statSync(`/${name}`).isDirectory()) continue;
      FS.mkdirTree(`/${name}`);
      FS.mount(FS.filesystems.NODEFS, { root: `/${name}` }, `/${name}`);
    } catch {
      // A folder this user cannot read is not the program's to read either.
    }
  }
}
// The kernel's packages, where this Python looks for installed ones (cad's build tells a model's own modules from
// installed ones by that folder).
const site = pyodide.runPython("import site; site.getsitepackages()[0]");
FS.mount(FS.filesystems.NODEFS, { root: path.join(home, "lib", `python${made.python}`, "site-packages") }, site);

// File facts the platform rounds or invents (a time to the millisecond, an inode of its own): the real ones, of a
// path, or of an open file (by the host's own descriptor for it, else by where it is).
const facts = (stat) => [stat.mode, stat.ino, stat.dev, stat.nlink, stat.uid, stat.gid, stat.size, stat.atimeNs,
  stat.mtimeNs, stat.ctimeNs].map(String);
const realStat = (file, follow) => {
  try {
    return facts((follow ? fs.statSync : fs.lstatSync)(file, { bigint: true }));
  } catch (error) {
    return error.code || "EIO";
  }
};
const NODEFS = FS.filesystems.NODEFS;
// Where an open file or folder is on the real filesystem; null for one that is not there (a pipe, a device, a
// file of the platform's own).
const openPath = (fd) => {
  const stream = FS.getStream(fd);
  if (!stream?.node || stream.node.mount?.type !== NODEFS) return null;
  try {
    return NODEFS.realPath(stream.node);
  } catch {
    return null;
  }
};
const openStat = (fd) => {
  const stream = FS.getStream(fd);
  if (!stream?.node || stream.node.mount?.type !== NODEFS) return "ENOTSUP";
  try {
    return facts(typeof stream.nfd === "number" ? fs.fstatSync(stream.nfd, { bigint: true })
      : fs.statSync(NODEFS.realPath(stream.node), { bigint: true }));
  } catch (error) {
    return error.code || "EIO";
  }
};
// A file's own number (its inode), which the platform replaces by one of its making wherever it answers a file's
// facts: the real one, so that every answer names the same file the same way (by path, by an open file, by a
// folder's entry), and as another process on this computer names it.
const attributes = NODEFS.getattr;
NODEFS.getattr = (read, node) => {
  let seen;
  const found = attributes(() => (seen = read()), node);
  if (seen && Number.isSafeInteger(seen.ino)) found.ino = seen.ino;
  return found;
};
// A file the program makes takes the mode it asked for less the process's mask, as on any system: the platform
// sets the mode asked for whole, after it makes the file.
const openFile = FS.open;
FS.open = (file, flags, mode) => openFile(file, flags, typeof mode === "number" ? mode & ~process.umask() : mode);

pyodide.globals.set("_host", pyodide.toPy({
  pid: process.pid,
  cwd: process.cwd(),
  executable: process.env.CAD_KERNEL_PYTHON || path.join(home, "bin", "python"),
  kind: run.kind,
  target: run.target,
  argv: run.argv,
  safe: run.safe,
  isolated: run.isolated,
  customize: run.site,
  site,
  mounted: process.platform !== "win32",
  libraries: fs.readdirSync(path.join(home, "lib", `python${made.python}`, "site-packages"))
    .filter((name) => name.endsWith(".libs")),
  deferred: made.deferred ?? [],
}));
// Sockets. The platform has none a program can use under Node, and the engine's own client is one: a program run
// here asks the engine's door for its builds. A thread of the host's does the asynchronous I/O (Node's `net`) and
// the program's thread, which cannot yield, waits on shared memory for each answer: connect, send, receive (with
// its time limit), close. Client stream sockets alone, to a port or a path; nothing listens here.
const NET = `
const { parentPort, workerData } = require("node:worker_threads");
const net = require("node:net");
const state = new Int32Array(workerData.state), data = new Uint8Array(workerData.data);
const held = new Map();
let last = 0;
function answer(status, bytes) {
  const length = bytes ? Math.min(bytes.length, data.length) : 0;
  if (length) data.set(bytes.subarray(0, length));
  Atomics.store(state, 1, status); Atomics.store(state, 2, length); Atomics.store(state, 0, 1); Atomics.notify(state, 0);
}
const failed = (error) => answer(-1, Buffer.from(String(error && (error.code || error.message) || "EIO")));
function give(one) {
  const asked = one.asked;
  if (!asked) return;
  if (one.chunks.length) {
    let chunk = one.chunks[0];
    if (chunk.length > asked.most) { one.chunks[0] = chunk.subarray(asked.most); chunk = chunk.subarray(0, asked.most); } else one.chunks.shift();
    clearTimeout(asked.timer); one.asked = null; answer(0, chunk);
  } else if (one.error) { clearTimeout(asked.timer); one.asked = null; failed(one.error);
  } else if (one.ended) { clearTimeout(asked.timer); one.asked = null; answer(0, null); }
}
parentPort.on("message", (said) => {
  const one = held.get(said.id);
  if (said.op === "connect") {
    const id = ++last, socket = net.connect(said.path ? { path: said.path } : { host: said.host, port: said.port });
    const made = { socket, chunks: [], ended: false, error: null, asked: null, open: false };
    const timer = said.seconds === null ? null : setTimeout(() => { if (!made.open) { socket.destroy(); held.delete(id); answer(-2, null); } }, said.seconds * 1000);
    socket.on("data", (chunk) => { made.chunks.push(chunk); give(made); });
    socket.on("end", () => { made.ended = true; give(made); });
    socket.on("close", () => { made.ended = true; give(made); });
    socket.on("error", (error) => {
      if (!made.open) { clearTimeout(timer); if (held.delete(id) || true) failed(error); return; }
      made.error = error; give(made);
    });
    socket.once("connect", () => { clearTimeout(timer); made.open = true; held.set(id, made); answer(id, null); });
  } else if (!one) { answer(-1, Buffer.from("EBADF"));
  } else if (said.op === "send") {
    one.socket.write(said.bytes, (error) => (error ? failed(error) : answer(said.bytes.length, null)));
  } else if (said.op === "receive") {
    one.asked = { most: Math.min(said.most, data.length),
                  timer: said.seconds === null ? null : setTimeout(() => { one.asked = null; answer(-2, null); }, said.seconds * 1000) };
    give(one);
  } else if (said.op === "close") { one.socket.destroy(); held.delete(said.id); answer(0, null); }
});
`;
let network = null;
function net(said) {
  if (network === null) {
    const state = new SharedArrayBuffer(12), data = new SharedArrayBuffer(1 << 20);
    const worker = new Worker(NET, { eval: true, workerData: { state, data } });
    worker.unref();
    network = { worker, state: new Int32Array(state), data: new Uint8Array(data) };
  }
  Atomics.store(network.state, 0, 0);
  network.worker.postMessage(said);
  Atomics.wait(network.state, 0, 0);
  const status = Atomics.load(network.state, 1), length = Atomics.load(network.state, 2);
  return [status, Uint8Array.from(network.data.subarray(0, length))];
}
pyodide.globals.set("_host_net", pyodide.toPy({
  connect: (host, port, file, seconds) => net({ op: "connect", host, port, path: file, seconds: seconds ?? null }),
  send: (id, bytes) => net({ op: "send", id, bytes: Uint8Array.from(bytes) }),
  receive: (id, most, seconds) => net({ op: "receive", id, most, seconds: seconds ?? null }),
  close: (id) => net({ op: "close", id }),
}, { depth: 1 }));

pyodide.globals.set("_host_files", pyodide.toPy({ stat: realStat, open_stat: openStat, open_path: openPath,
  umask: (mask) => process.umask(mask),
  // The folder the process itself stands in, which the system sees (a folder a process stands in is held).
  chdir: (folder) => { try { process.chdir(folder); return true; } catch { return false; } } }, { depth: 1 }));
// Beside the standard library's extension modules: on the path already, and a library's module to a build (cad's
// build forgets a model's own modules between builds, which it tells from libraries' by where their files are).
const dynload = pyodide.runPython("import sysconfig; sysconfig.get_path('stdlib') + '/lib-dynload'");
pyodide.FS.writeFile(`${dynload}/_cad_bootstrap.py`, fs.readFileSync(path.join(HERE, "bootstrap.py"), "utf8"));
let code = 0;
try {
  code = pyodide.runPython("import _cad_bootstrap; _cad_bootstrap.main(_host, _host_files, _host_net)");
} catch (error) {
  fs.writeSync(2, `${String(error?.message ?? error)}\n`);
  code = 1;
}
process.exit(typeof code === "number" ? code : 0);
