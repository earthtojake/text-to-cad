// Benchmark the view core in headless Chromium: a Worker running hosts/web/viewcore.js, driven from a page.
//
//   node web_bench.mjs OUT_DIR [--wasm dist/viewcore.wasm] [--throttle 4] [--picks 100] [--headed]
//                      [--files DIR] NAME_OR_FILE.xbf [...]
//
// Per model one fresh page + Worker (cold). Writes OUT_DIR/<stem>/ in reference.py's layout (the bytes the core
// returned, so compare.py can check browser vs wasmtime byte for byte) plus timing.json, and prints one JSON line
// per model. Timings are measured in the page around Worker round trips (transfers included) unless named *_core_*,
// which are the Worker's own time inside the call.
import http from "node:http";
import fs from "node:fs";
import path from "node:path";
import { execFileSync } from "node:child_process";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const { chromium } = require("playwright");
const HERE = path.dirname(fileURLToPath(import.meta.url));
const PKG = path.resolve(HERE, "..");

const args = process.argv.slice(2);
const opt = { wasm: path.join(PKG, "dist", "viewcore.wasm"), throttle: 1, picks: 100, headed: false, files: path.join(PKG, "tmp", "files") };
const pos = [];
for (let i = 0; i < args.length; i++) {
  const a = args[i];
  if (a === "--wasm") opt.wasm = path.resolve(args[++i]);
  else if (a === "--throttle") opt.throttle = Number(args[++i]);
  else if (a === "--picks") opt.picks = Number(args[++i]);
  else if (a === "--files") opt.files = path.resolve(args[++i]);
  else if (a === "--headed") opt.headed = true;
  else pos.push(a);
}
if (pos.length < 2) { console.error("usage: node web_bench.mjs OUT_DIR [options] NAME_OR_FILE.xbf ..."); process.exit(2); }
const outDir = path.resolve(pos[0]);
const models = pos.slice(1).map((n) => (n.endsWith(".xbf") ? path.resolve(n) : path.join(opt.files, n + ".xbf")));

const PAGE = `<!doctype html><meta charset=utf-8><title>viewcore bench</title><script type="module">
const post = (p, body) => fetch("/out/" + p, { method: "POST", body });
function rng(seed) { return () => { seed |= 0; seed = (seed + 0x6D2B79F5) | 0; let t = Math.imul(seed ^ (seed >>> 15), 1 | seed); t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296; }; }
const now = () => performance.now() / 1000;
const median = (a) => { const s = [...a].sort((x, y) => x - y); const n = s.length; return n ? (n % 2 ? s[(n - 1) / 2] : (s[n / 2 - 1] + s[n / 2]) / 2) : null; };
const p95 = (a) => { const s = [...a].sort((x, y) => x - y); return s.length ? s[Math.min(s.length - 1, Math.floor(0.95 * s.length))] : null; };

window.runBench = async (model, xbfUrl, wasmUrl, picks) => {
  const worker = new Worker("/hosts/web/worker.js", { type: "module" });
  let nextId = 1; const waiting = new Map();
  worker.onmessage = (e) => { const w = waiting.get(e.data.id); waiting.delete(e.data.id); e.data.ok ? w.resolve(e.data) : w.reject(new Error(e.data.error)); };
  worker.onerror = (e) => { for (const w of waiting.values()) w.reject(new Error("worker error: " + e.message)); };
  const rpc = (msg, transfer = []) => new Promise((resolve, reject) => { const id = nextId++; waiting.set(id, { resolve, reject }); worker.postMessage({ id, ...msg }, transfer); });
  const T = {}; const out = { model, errors: [] };
  const timed = async (name, fn) => { const t = now(); const r = await fn(); T[name] = now() - t; return r; };
  const t0 = now();
  // wasm fetch as a plain download (what the network costs), the xbf fetch, and the Worker's own streaming compile in parallel
  const [xbf, , init] = await Promise.all([
    timed("fetch_xbf_s", async () => new Uint8Array(await (await fetch(xbfUrl)).arrayBuffer())),
    timed("fetch_wasm_s", async () => (await fetch(wasmUrl)).arrayBuffer()),
    timed("init_total_s", () => rpc({ op: "init", url: wasmUrl })),
  ]);
  T.compile_s = init.result.compileMs / 1000; T.instantiate_s = init.result.instantiateMs / 1000;
  out.occt = init.result.occt;
  const { doc } = (await timed("open_s", () => rpc({ op: "open", bytes: xbf }, [xbf.buffer]))).result;
  const sres = await timed("structure_s", () => rpc({ op: "structureBytes", doc }));
  await post(model + "/structure.json", sres.result);
  const structure = JSON.parse(new TextDecoder().decode(sres.result));
  const protos = structure.prototypes;
  const groups = new Map(); // key -> [indices]
  for (const p of protos) { if (!groups.has(p.key)) groups.set(p.key, []); groups.get(p.key).push(p.index); }
  const uniq = [...groups.entries()].map(([key, idx]) => ({ key, idx, part: idx[0] }));
  const save = (u, name, bytes) => post(model + "/" + name + "?parts=" + u.idx.join(","), bytes);
  for (const p of protos) await post(model + "/key?parts=" + p.index, new TextEncoder().encode(p.key));
  // first mesh, as the viewer wants it
  const first = uniq[0];
  let core = {};
  if (first) {
    const r = await timed("first_mesh_s", () => rpc({ op: "mesh", doc, part: first.part }));
    T.cold_to_first_mesh_s = now() - t0;
    core.first_mesh_core_s = r.ms / 1000;
    await save(first, "mesh.xbm", r.result);
  }
  const stage = async (name, op, file, skipFirst) => {
    let total = 0, coreMs = 0;
    for (const u of uniq) {
      if (skipFirst && u === first) continue;
      const t = now(); const r = await rpc({ op, doc, part: u.part }); total += now() - t; coreMs += r.ms;
      await save(u, file, r.result);
    }
    T[name] = total; core[name.replace("_s", "_core_s")] = coreMs / 1000;
  };
  await stage("shape_bytes_s", "shapeBytes", "shape.bin");
  await stage("mesh_s", "mesh", "mesh.xbm", true); T.mesh_s += T.first_mesh_s || 0; // all meshes = first + the rest
  core.mesh_core_s += core.first_mesh_core_s || 0;
  await stage("elements_s", "elementsBytes", "elements.json");
  await stage("groups_s", "groupsBytes", "groups.json");
  await stage("measure_s", "measureBytes", "measure.json");
  // picks: seeded random face/edge facts
  const pool = [];
  for (const u of uniq) {
    const el = JSON.parse(new TextDecoder().decode((await rpc({ op: "elementsBytes", doc, part: u.part })).result));
    for (const o of Object.keys(el.faces || {})) pool.push([u.part, "face", +o]);
    for (const o of Object.keys(el.edges || {})) pool.push([u.part, "edge", +o]);
  }
  const rand = rng(0); const rt = [], cr = [];
  for (let i = 0; pool.length && i < picks; i++) {
    const [part, kind, ordinal] = pool[Math.floor(rand() * pool.length)];
    const t = now(); const r = await rpc({ op: "factBytes", doc, part, kind, ordinal }); rt.push(now() - t); cr.push(r.ms / 1000);
  }
  Object.assign(T, { pick_median_s: median(cr), pick_p95_s: p95(cr), pick_roundtrip_median_s: median(rt), pick_roundtrip_p95_s: p95(rt), picks: rt.length });
  T.wasm_memory_mb = (await rpc({ op: "memory" })).result.memoryBytes / 2 ** 20;
  T.total_s = now() - t0;
  Object.assign(T, { parts: protos.length, keys: uniq.length, instances: structure.instances.length, wasm_bytes: undefined, ...core });
  await rpc({ op: "close", doc });
  worker.terminate();
  return T;
};
</script>`;

// -- server: static files, wasm, xbf, and POST /out/<model>/<file>?parts=1,2 writing into OUT_DIR
const wasmBytes = fs.readFileSync(opt.wasm).length;
const server = http.createServer((req, res) => {
  const url = new URL(req.url, "http://x");
  const send = (code, type, body) => { res.writeHead(code, { "content-type": type, "cache-control": "no-store" }); res.end(body); };
  if (req.method === "POST" && url.pathname.startsWith("/out/")) {
    const chunks = [];
    req.on("data", (c) => chunks.push(c));
    req.on("end", () => {
      const rel = decodeURIComponent(url.pathname.slice(5)).split("/");
      const [model, file] = [rel[0], rel.slice(1).join("/")];
      const body = Buffer.concat(chunks);
      const parts = url.searchParams.get("parts");
      const targets = parts ? parts.split(",").map((i) => path.join(outDir, model, "parts", i, file)) : [path.join(outDir, model, file)];
      for (const t of targets) { fs.mkdirSync(path.dirname(t), { recursive: true }); fs.writeFileSync(t, body); }
      send(200, "text/plain", "ok");
    });
    return;
  }
  if (url.pathname === "/") return send(200, "text/html", PAGE);
  if (url.pathname === "/viewcore.wasm") return send(200, "application/wasm", fs.readFileSync(opt.wasm));
  if (url.pathname.startsWith("/hosts/web/")) {
    const f = path.join(PKG, "hosts", "web", path.basename(url.pathname));
    if (fs.existsSync(f)) return send(200, "text/javascript", fs.readFileSync(f));
  }
  if (url.pathname.startsWith("/xbf/")) {
    const f = models.find((m) => path.basename(m) === path.basename(url.pathname));
    if (f) return send(200, "application/octet-stream", fs.readFileSync(f));
  }
  send(404, "text/plain", "not found");
});
await new Promise((r) => server.listen(0, "127.0.0.1", r));
const base = `http://127.0.0.1:${server.address().port}`;

const browser = await chromium.launch({ headless: !opt.headed });
console.error("chromium", browser.version(), "throttle", opt.throttle);

function rendererRssKb() {
  try {
    const out = execFileSync("ps", ["-eo", "rss,args"], { encoding: "utf8" });
    let sum = 0, max = 0;
    for (const line of out.split("\n")) {
      if (!line.includes("--type=renderer")) continue;
      const rss = parseInt(line.trim(), 10);
      sum += rss; max = Math.max(max, rss);
    }
    return { sum, max };
  } catch { return { sum: 0, max: 0 }; }
}

for (const model of models) {
  const stem = path.basename(model, ".xbf");
  const context = await browser.newContext();
  const page = await context.newPage();
  page.on("console", (m) => { if (m.type() === "error") console.error("[page]", m.text()); });
  page.on("pageerror", (e) => console.error("[pageerror]", e.message));
  await page.goto(base + "/");
  if (opt.throttle > 1) {
    const cdp = await context.newCDPSession(page);
    await cdp.send("Emulation.setCPUThrottlingRate", { rate: opt.throttle });
  }
  const base0 = rendererRssKb();
  let peakSum = base0.sum, peakMax = base0.max;
  const timer = setInterval(() => { const r = rendererRssKb(); peakSum = Math.max(peakSum, r.sum); peakMax = Math.max(peakMax, r.max); }, 50);
  let result;
  try {
    result = await page.evaluate(([m, x, w, p]) => window.runBench(m, x, w, p), [stem, `${base}/xbf/${path.basename(model)}`, `${base}/viewcore.wasm`, opt.picks]);
  } catch (e) {
    result = { error: String(e.message || e) };
  }
  clearInterval(timer);
  const r = rendererRssKb(); peakSum = Math.max(peakSum, r.sum); peakMax = Math.max(peakMax, r.max);
  Object.assign(result, { peak_renderer_rss_mb: +(peakMax / 1024).toFixed(1), peak_renderer_rss_sum_mb: +(peakSum / 1024).toFixed(1),
    baseline_renderer_rss_mb: +(base0.max / 1024).toFixed(1), wasm_file_bytes: wasmBytes, throttle: opt.throttle });
  for (const k of Object.keys(result)) if (result[k] === undefined || result[k] === null) delete result[k];
  for (const k of Object.keys(result)) if (typeof result[k] === "number" && !Number.isInteger(result[k])) result[k] = +result[k].toFixed(5);
  fs.mkdirSync(path.join(outDir, stem), { recursive: true });
  fs.writeFileSync(path.join(outDir, stem, "timing.json"), JSON.stringify(result));
  console.log(JSON.stringify({ file: stem + ".xbf", ...result }));
  await context.close();
}
await browser.close();
server.close();
