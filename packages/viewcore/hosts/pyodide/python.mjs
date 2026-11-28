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
//   - `sys.path` as CPython makes it: the script's folder (unless -P), PYTHONPATH, then the kernel folder's
//     site-packages.
//
// What it cannot be: a Python with threads, child processes or sockets. A program that starts one fails there, as
// on any Pyodide.
//
// The kernel folder is named by CAD_KERNEL_HOME, or is the folder two above this file's launcher (make.mjs writes
// `KERNEL/bin/python`, which sets it).
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

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
const run = { safe: false, unbuffered: false, xoptions: [], kind: null, target: null, argv: [] };
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
      if (letter === "P" || letter === "I") run.safe = true;
      else if (letter === "u") run.unbuffered = true;
      else if (!"BEsSqOdvb".includes(letter)) refuse(`unknown option -${letter}`);
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
  site,
  mounted: process.platform !== "win32",
  libraries: fs.readdirSync(path.join(home, "lib", `python${made.python}`, "site-packages"))
    .filter((name) => name.endsWith(".libs")),
  deferred: made.deferred ?? [],
}));
pyodide.globals.set("_host_files", pyodide.toPy({ stat: realStat, open_stat: openStat, open_path: openPath,
  umask: (mask) => process.umask(mask) }, { depth: 1 }));
// Beside the standard library's extension modules: on the path already, and a library's module to a build (cad's
// build forgets a model's own modules between builds, which it tells from libraries' by where their files are).
const dynload = pyodide.runPython("import sysconfig; sysconfig.get_path('stdlib') + '/lib-dynload'");
pyodide.FS.writeFile(`${dynload}/_cad_bootstrap.py`, fs.readFileSync(path.join(HERE, "bootstrap.py"), "utf8"));
let code = 0;
try {
  code = pyodide.runPython("import _cad_bootstrap; _cad_bootstrap.main(_host, _host_files)");
} catch (error) {
  fs.writeSync(2, `${String(error?.message ?? error)}\n`);
  code = 1;
}
process.exit(typeof code === "number" ? code : 0);
