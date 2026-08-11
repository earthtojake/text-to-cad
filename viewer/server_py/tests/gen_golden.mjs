#!/usr/bin/env node
// Generates golden.json from the REAL JS semantics so the Python ports can be
// asserted byte-for-byte. Run: node viewer/server_py/tests/gen_golden.mjs
// (Re-run whenever the JS encoders change; this file is the parity spec.)
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

function encodeContentDispositionFilename(value) {
  return encodeURIComponent(value).replace(/['()*]/g, (char) => (
    `%${char.charCodeAt(0).toString(16).toUpperCase()}`
  ));
}
function downloadFilename(value) {
  const rawFilename = path.basename(String(value || "").replace(/\\/g, "/")) || "download";
  return rawFilename.replace(/[\x00-\x1f"\\]/g, "_");
}
function attachmentContentDisposition(filename) {
  const safeFilename = downloadFilename(filename);
  const quotedFilename = safeFilename.replace(/[^\x20-\x7e]/g, "_");
  return `attachment; filename="${quotedFilename}"; filename*=UTF-8''${encodeContentDispositionFilename(safeFilename)}`;
}
function localAssetUrl(file, dir, v) {
  const url = new URL("/__cad/asset", "http://cad.local");
  url.searchParams.set("file", file);
  if (dir) url.searchParams.set("dir", dir);
  if (v) url.searchParams.set("v", v);
  return `${url.pathname}${url.search}`;
}
function compareEntries(a, b) {
  return String(a).localeCompare(String(b), undefined, { numeric: true, sensitivity: "base" });
}

const encodeStrings = [
  "a b(c)*d~e._-", "résumé (1).glb", "plain.glb", "with space.stl",
  "weird'name\".step", "100% done.3mf", "ünïcödé/path seg.glb", "a+b=c&d.glb",
  "tilde~name.glb", "()*!'safe.glb",
];
const filenames = [
  "model.glb", "résumé (1).glb", "bad\\name\"x.stl", "../escape.glb",
  "with\ttab.3mf", "ünïcödé.step", "", "no-ext",
];
const base36Values = [0, 1, 35, 36, 2158, 1719440100123, "1719440100123456789"];
const assetUrls = [
  ["/abs/p a th/x(1).glb", "/root dir", "zz-1a"],
  ["/abs/plain.glb", "", ""],
  ["/abs/ünï.glb", "/r", "1-2"],
  ["/abs/tilde~.glb", "", "abc"],
];
const sortLists = [
  ["file10.step", "file2.step", "File1.step", "alpha.STL", "alpha.stl"],
  ["b/10.glb", "b/9.glb", "b/1.glb", "a/2.glb"],
  ["Item-2", "item-10", "ITEM-1", "item-2"],
  // punctuation/boundary collation (the cases that break naive codepoint sort)
  ["servo_end_mount.3mf", "servo_end_mount_double.3mf", "servo_horn_yoke.3mf", "servo_horn_yoke_double_horn.3mf"],
  ["mount.x", "mount_d.x", "mountd.x", "mount2.x"],
  ["a b", "a_b", "a-b", "a.b", "a+b", "a~b", "ab", "a1"],
  ["v2.10", "v2.9", "v10.1", "v2.1"],
];

const golden = {
  encodeUriComponent: Object.fromEntries(encodeStrings.map((s) => [s, encodeURIComponent(s)])),
  contentDisposition: Object.fromEntries(filenames.map((s) => [s, attachmentContentDisposition(s)])),
  base36: Object.fromEntries(base36Values.map((v) => [String(v), BigInt(v).toString(36)])),
  assetUrls: assetUrls.map(([file, dir, v]) => ({ file, dir, v, url: localAssetUrl(file, dir, v) })),
  sort: sortLists.map((list) => ({ input: list, sorted: [...list].sort(compareEntries) })),
};

const outPath = path.join(path.dirname(fileURLToPath(import.meta.url)), "golden.json");
fs.writeFileSync(outPath, JSON.stringify(golden, null, 2) + "\n");
console.log(`wrote ${outPath}`);
