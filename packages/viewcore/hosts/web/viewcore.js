// Browser host of the view core (viewcore.wasm): an ES module, usable in a page or a Worker.
//
//   const core = await Core.load("/dist/viewcore.wasm");
//   const doc = core.openXbf(new Uint8Array(await (await fetch("m.xbf")).arrayBuffer()));
//   doc.structure(); doc.mesh(0); doc.fact(0, "face", 1); doc.close();
//
// Binary results (shapeBytes, mesh, *Bytes) are Uint8Array copies that own their ArrayBuffer (transferable).
// Errors throw ViewCoreError with vc_last_error's text. The WASI shim provides exactly the wasi_snapshot_preview1
// imports the module declares (any name it does not implement answers ENOSYS), nothing else.

export class ViewCoreError extends Error {}

/**
 * Whether `error` is the module faulting (a WebAssembly trap: memory out of bounds, unreachable, the stack
 * overflowed) rather than refusing: the instance's memory and its stack pointer are left as the trap found them, so
 * it must not run again. Core.renew() starts a fresh one from the same compiled module.
 */
export function isFault(error) {
  return error instanceof WebAssembly.RuntimeError || (error instanceof RangeError && /call stack/i.test(error.message));
}

// The least WebAssembly module with a 128-bit SIMD instruction: an engine that cannot validate it cannot run the core.
const SIMD_PROBE = new Uint8Array([0, 97, 115, 109, 1, 0, 0, 0, 1, 5, 1, 96, 0, 1, 123, 3, 2, 1, 0, 10, 22, 1, 20, 0,
  253, 12, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 11]);

/** Refused in one line where this WebAssembly engine has no 128-bit SIMD, which the module is built with. */
export function needSimd() {
  if (!WebAssembly.validate(SIMD_PROBE)) {
    throw new ViewCoreError("this WebAssembly engine has no 128-bit SIMD, which the view core needs (Node 16.4, Chrome 91, " +
      "Firefox 89, Safari 16.4, wasmtime 0.33 or later)");
  }
}

// An int32 the core is given (an ordinal, a part's place): a whole number in range, never one ToInt32 would wrap.
function int32(value, what) {
  if (!Number.isInteger(value) || value < -(2 ** 31) || value >= 2 ** 31) throw new ViewCoreError(`${what} is not a 32-bit whole number: ${value}`);
  return value;
}

const KINDS = { face: 0, edge: 1, vertex: 2 };
const ERRNO = { SUCCESS: 0, BADF: 8, INVAL: 28, NOSYS: 52 };

function makeWasi(getMemory, log) {
  const mem = () => getMemory();
  const dv = () => new DataView(mem().buffer);
  const u8 = () => new Uint8Array(mem().buffer);
  const decoder = new TextDecoder();
  const lines = { 1: "", 2: "" };
  const flush = (fd, s) => {
    lines[fd] += s;
    let i;
    while ((i = lines[fd].indexOf("\n")) >= 0) {
      log(fd, lines[fd].slice(0, i));
      lines[fd] = lines[fd].slice(i + 1);
    }
  };
  const impl = {
    fd_write(fd, iovs, iovsLen, nwrittenPtr) {
      const d = dv(), m = u8();
      let n = 0;
      for (let i = 0; i < iovsLen; i++) {
        const p = d.getUint32(iovs + i * 8, true), l = d.getUint32(iovs + i * 8 + 4, true);
        if (fd === 1 || fd === 2) flush(fd, decoder.decode(m.subarray(p, p + l), { stream: true }));
        n += l;
      }
      d.setUint32(nwrittenPtr, n, true);
      return fd === 1 || fd === 2 ? ERRNO.SUCCESS : ERRNO.BADF;
    },
    fd_close: () => ERRNO.SUCCESS,
    fd_seek: () => ERRNO.NOSYS, // ESPIPE-like: not seekable; stdio never seeks
    fd_fdstat_get: () => ERRNO.BADF,
    clock_time_get(id, _precision, outPtr) {
      // 0 realtime, 1 monotonic, others (cpu time) approximated by monotonic
      const ns = id === 0 ? BigInt(Math.round(Date.now() * 1e6)) : BigInt(Math.round(performance.now() * 1e6));
      dv().setBigUint64(outPtr, ns, true);
      return ERRNO.SUCCESS;
    },
    clock_res_get(_id, outPtr) { dv().setBigUint64(outPtr, 1000n, true); return ERRNO.SUCCESS; },
    random_get(ptr, len) {
      const view = u8().subarray(ptr, ptr + len);
      for (let o = 0; o < len; o += 65536) crypto.getRandomValues(view.subarray(o, Math.min(len, o + 65536)));
      return ERRNO.SUCCESS;
    },
    environ_sizes_get(countPtr, sizePtr) { const d = dv(); d.setUint32(countPtr, 0, true); d.setUint32(sizePtr, 0, true); return 0; },
    environ_get: () => ERRNO.SUCCESS,
    args_sizes_get(countPtr, sizePtr) { const d = dv(); d.setUint32(countPtr, 0, true); d.setUint32(sizePtr, 0, true); return 0; },
    args_get: () => ERRNO.SUCCESS,
    proc_exit(code) { throw new ViewCoreError(`proc_exit(${code}) called by the core`); },
    sched_yield: () => ERRNO.SUCCESS,
  };
  return impl;
}

export class Core {
  /** Load from a URL (streaming compile when the server sends application/wasm), or from bytes / a Module. */
  static async load(source, opts = {}) {
    needSimd();
    const t0 = performance.now();
    let module, fetchMs = 0, bytes = 0;
    if (source instanceof WebAssembly.Module) {
      module = source;
    } else if (source instanceof ArrayBuffer || ArrayBuffer.isView(source)) {
      module = await WebAssembly.compile(source);
    } else {
      const response = await fetch(source);
      if (!response.ok) throw new ViewCoreError(`fetch ${source}: ${response.status}`);
      const type = response.headers.get("content-type") || "";
      if (type.startsWith("application/wasm") && WebAssembly.compileStreaming) {
        module = await WebAssembly.compileStreaming(response);
      } else {
        const buf = await response.arrayBuffer();
        fetchMs = performance.now() - t0;
        bytes = buf.byteLength;
        module = await WebAssembly.compile(buf);
      }
    }
    const compileMs = performance.now() - t0; // fetch + compile (overlapped when streaming)
    const core = await Core.instantiate(module, opts);
    core.compileMs = compileMs;
    core.fetchMs = fetchMs;
    return core;
  }

  static async instantiate(module, opts = {}) {
    const t0 = performance.now();
    const log = opts.log || ((fd, line) => (fd === 2 ? console.error : console.log)("[core]", line));
    let memory = null;
    const wasi = makeWasi(() => memory, log);
    const imports = {};
    for (const { module: m, name, kind } of WebAssembly.Module.imports(module)) {
      imports[m] ??= {};
      if (m === "wasi_snapshot_preview1") {
        imports[m][name] = wasi[name] || (() => ERRNO.NOSYS);
      } else if (m === "env" && name === "emscripten_notify_memory_growth" && kind === "function") {
        imports[m][name] = () => {}; // views are re-taken on every call
      } else {
        throw new ViewCoreError(`the module imports ${m}.${name}, which the host does not provide`);
      }
    }
    const instance = await WebAssembly.instantiate(module, imports);
    memory = instance.exports.memory;
    const core = new Core(instance, memory);
    core.module = module;
    core.opts = opts;
    if (instance.exports._initialize) instance.exports._initialize();
    core.instantiateMs = performance.now() - t0;
    if (core.x.vc_abi_version() !== 4) throw new ViewCoreError("unsupported ABI version " + core.x.vc_abi_version());
    return core;
  }

  constructor(instance, memory) {
    this.instance = instance;
    this.x = instance.exports;
    this.memory = memory;
    this.module = null;
    this.opts = {};
    this.generation = 0; // a Doc opened in another generation is gone with the instance it lived in
    this.compileMs = 0;
    this.instantiateMs = 0;
    this.lenPtr = this.x.vc_alloc(4) >>> 0; // out-length cell, reused
  }

  /**
   * A fresh instance of the same compiled module in place of this one, after a fault (isFault): its memory, its
   * documents and parts are let go, and a Doc opened before refuses from now on.
   */
  async renew() {
    const fresh = await Core.instantiate(this.module, this.opts);
    this.instance = fresh.instance;
    this.x = fresh.x;
    this.memory = fresh.memory;
    this.lenPtr = fresh.lenPtr;
    this.generation += 1;
  }

  get memoryBytes() { return this.memory.buffer.byteLength; }
  get occtVersion() { return this.cstr(this.x.vc_occt_version() >>> 0); }
  lastError() { return this.cstr(this.x.vc_last_error() >>> 0); }

  cstr(ptr) {
    if (!ptr) return "";
    const m = new Uint8Array(this.memory.buffer);
    let e = ptr;
    while (m[e] !== 0) e++;
    return new TextDecoder().decode(m.subarray(ptr, e));
  }

  fail(what) { throw new ViewCoreError(`${what}: ${this.lastError() || "unknown error"}`); }

  /** Call a vc_* function that returns a core buffer (args, then the out-length pointer); copy it out and free it. */
  result(name, ...args) {
    const ptr = this.x[name](...args, this.lenPtr) >>> 0;
    if (!ptr) this.fail(name);
    const n = new DataView(this.memory.buffer).getUint32(this.lenPtr, true);
    const out = new Uint8Array(this.memory.buffer, ptr, n).slice(); // own buffer
    this.x.vc_free(ptr);
    return out;
  }

  /** Open an .xbf's bytes; `stem` names the document where its file does not (the file's stem). */
  openXbf(data, stem = "") {
    const bytes = data instanceof Uint8Array ? data : new Uint8Array(data);
    const name = new TextEncoder().encode(String(stem || ""));
    const n = bytes.length;
    const ptr = this.x.vc_alloc(n + name.length) >>> 0;
    if (!ptr && n) this.fail("vc_alloc");
    let h;
    try {
      const into = new Uint8Array(this.memory.buffer, ptr, n + name.length);
      into.set(bytes);
      into.set(name, n);
      h = this.x.vc_open_xbf(ptr, n, ptr + n, name.length);
    } finally {
      this.x.vc_free(ptr);
    }
    if (!h) this.fail("vc_open_xbf");
    return new Doc(this, h);
  }

  /** Bytes copied into the module, handed to `use(ptr, length)` and freed after it. */
  given(bytes, use) {
    const n = bytes.length;
    const ptr = this.x.vc_alloc(n) >>> 0;
    if (!ptr && n) this.fail("vc_alloc");
    try {
      new Uint8Array(this.memory.buffer, ptr, n).set(bytes);
      return use(ptr, n);
    } finally {
      this.x.vc_free(ptr);
    }
  }

  /**
   * A still drawn in software (vc_render): `scene` as include/viewcore.h says it, `payloads` the buffers it names
   * by their place in this list (meshes, the environment, textures). Width x height RGBA bytes, sRGB, the top row
   * first; or a PNG where `scene.format` is "png".
   */
  render(scene, payloads = []) {
    const parts = payloads.map((p) => (p instanceof Uint8Array ? p : new Uint8Array(p)));
    const text = new TextEncoder().encode(JSON.stringify({ ...scene, payloads: parts.map((p) => p.length) }));
    const total = parts.reduce((n, p) => n + p.length, 0);
    const ptr = this.x.vc_alloc(text.length + total) >>> 0;
    if (!ptr) this.fail("vc_alloc");
    try {
      const into = new Uint8Array(this.memory.buffer, ptr, text.length + total);
      into.set(text);
      let at = text.length;
      for (const part of parts) {
        into.set(part, at);
        at += part.length;
      }
      return this.result("vc_render", ptr, text.length, ptr + text.length, total);
    } finally {
      this.x.vc_free(ptr);
    }
  }

  /** A part's canonical shape bytes opened by themselves (the engine's pool jobs): a Doc of one part, index 0. */
  openShape(data) {
    const bytes = data instanceof Uint8Array ? data : new Uint8Array(data);
    const h = this.given(bytes, (ptr, n) => this.x.vc_open_shape(ptr, n));
    if (!h) this.fail("vc_open_shape");
    return new Doc(this, h);
  }
}

const json = (u8) => JSON.parse(new TextDecoder().decode(u8));

/** The exports the core writes, by the viewer's format name, each its vc_* function. */
export const EXPORTS = Object.freeze({ step: "vc_step", stl: "vc_stl", threemf: "vc_3mf", glb: "vc_glb" });

export class Doc {
  constructor(core, handle) { this.core = core; this.handle = handle; this.generation = core.generation; }
  /** The handle, where the document still lives (not closed, not let go with a faulted instance). */
  get h() {
    if (!this.handle) throw new ViewCoreError("the document is closed");
    if (this.generation !== this.core.generation) throw new ViewCoreError("the document was let go when the core faulted: open it again");
    return this.handle;
  }
  structureBytes() { return this.core.result("vc_structure", this.h); }
  structure() { return json(this.structureBytes()); }
  shapeBytes(part) { return this.core.result("vc_shape_bytes", this.h, int32(part, "a part")); }
  mesh(part) { return this.core.result("vc_mesh", this.h, int32(part, "a part")); }
  /** The part meshed to an export's own ceilings (mm, degrees; none where not a positive number); never kept. */
  meshAt(part, tolerance, angle) {
    return this.core.result("vc_mesh_at", this.h, int32(part, "a part"), tolerance > 0 ? tolerance : 0, angle > 0 ? angle : 0);
  }
  /** The faces the part's last mesh left without triangles, each with what was said of it: { ordinal: text }. */
  unmeshedBytes(part) { return this.core.result("vc_unmeshed", this.h, int32(part, "a part")); }
  unmeshed(part) { return json(this.unmeshedBytes(part)); }
  /** The part's whole table with the caller's unmeshed ordinals checked (the engine's `elements(unmeshed)`). */
  tableBytes(part, unmeshed = []) {
    const ordinals = Int32Array.from(unmeshed, (ordinal) => int32(ordinal, "an unmeshed ordinal"));
    return this.core.given(new Uint8Array(ordinals.buffer), (ptr) =>
      this.core.result("vc_table", this.h, int32(part, "a part"), ptr, ordinals.length));
  }
  factBytes(part, kind, ordinal) {
    const code = typeof kind === "string" ? KINDS[kind] : kind;
    if (code !== 0 && code !== 1 && code !== 2) throw new ViewCoreError(`no kind ${kind}: face, edge or vertex`);
    return this.core.result("vc_fact", this.h, int32(part, "a part"), code, int32(ordinal, "an ordinal"));
  }
  fact(part, kind, ordinal) { return json(this.factBytes(part, kind, ordinal)); }
  groupsBytes(part) { return this.core.result("vc_groups", this.h, int32(part, "a part")); }
  groups(part) { return json(this.groupsBytes(part)); }
  elementsBytes(part) { return this.core.result("vc_elements", this.h, int32(part, "a part")); }
  elements(part) { return json(this.elementsBytes(part)); }
  measureBytes(part) { return this.core.result("vc_measure", this.h, int32(part, "a part")); }
  measure(part) { return json(this.measureBytes(part)); }
  /** The whole document as a file, as `cad export` writes it: `format` one of EXPORTS' keys. */
  exportBytes(format) {
    const fn = EXPORTS[format];
    if (!fn) throw new ViewCoreError(`the core exports no ${format}`);
    return this.core.result(fn, this.h);
  }
  close() {
    if (this.handle && this.generation === this.core.generation) this.core.x.vc_close(this.handle);
    this.handle = 0;
  }
}
