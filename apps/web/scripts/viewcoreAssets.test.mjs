import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";

import { VIEW_CORE_LICENCES, viewCoreAssets } from "./viewcoreAssets.mjs";

const REPO = path.resolve(path.dirname(new URL(import.meta.url).pathname), "../../..");

/** A checkout of the files the build reads, in a temporary folder: a module where `wasm`, the licences where `licences`. */
function checkout(t, { wasm = true, licences = true } = {}) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "viewcore-assets-"));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const put = (at, bytes) => {
    fs.mkdirSync(path.dirname(path.join(root, at)), { recursive: true });
    fs.writeFileSync(path.join(root, at), bytes);
  };
  if (wasm) put("packages/viewcore/dist/viewcore.wasm", Buffer.from([0, 97, 115, 109]));
  put("packages/viewcore/hosts/web/viewcore.js", "export {};\n");
  put("packages/viewcore/hosts/web/worker.js", "export {};\n");
  if (licences) for (const name of VIEW_CORE_LICENCES) put(`packages/viewcore/licenses/${name}`, `the text of ${name}\n`);
  return root;
}

test("the module ships with OCCT's licence texts and a notice naming them", (t) => {
  const files = viewCoreAssets(checkout(t), {});
  for (const name of VIEW_CORE_LICENCES) assert.equal(files[name].toString(), `the text of ${name}\n`);
  const notice = files["NOTICE.txt"].toString();
  for (const name of [...VIEW_CORE_LICENCES, "Open CASCADE", "V8_0_1"]) assert.match(notice, new RegExp(name));
  const manifest = JSON.parse(files["manifest.json"].toString());
  assert.deepEqual(manifest.licences, VIEW_CORE_LICENCES.map(name => `/viewcore/${name}`));
});

test("no module, nothing shipped; a module without its licence texts is no build", (t) => {
  assert.equal(viewCoreAssets(checkout(t, { wasm: false }), {}), null);
  assert.equal(viewCoreAssets(checkout(t), { CAD_VIEWCORE: "0" }), null);
  assert.throws(() => viewCoreAssets(checkout(t, { licences: false }), {}), /ENOENT/);
});

test("the licence texts are OCCT's own, as its tag V8_0_1 holds them", () => {
  const held = (name) => fs.readFileSync(path.join(REPO, "packages/viewcore/licenses", name), "utf8");
  assert.match(held("LICENSE_LGPL_21.txt"), /GNU LESSER GENERAL PUBLIC LICENSE\s+Version 2\.1, February 1999/);
  assert.match(held("OCCT_LGPL_EXCEPTION.txt"), /Open CASCADE exception \(version 1\.0\) to GNU LGPL version 2\.1/);
});
