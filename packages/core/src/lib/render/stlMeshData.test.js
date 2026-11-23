import assert from "node:assert/strict";
import test from "node:test";

import * as THREE from "three";
import { toCreasedNormals } from "three/examples/jsm/utils/BufferGeometryUtils.js";

import { buildMeshDataFromStlBuffer, buildMeshDataFromStlGeometry, readableStlBuffer } from "./stlMeshData.js";

test("buildMeshDataFromStlGeometry recomputes crease-aware STL display normals", () => {
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute(
    "position",
    new THREE.Float32BufferAttribute([
      0, 0, 0,
      1, 0, 0,
      1, 1, 0,
      0, 0, 0,
      1, 1, 0,
      0, 1, 0
    ], 3)
  );
  geometry.setAttribute(
    "normal",
    new THREE.Float32BufferAttribute([
      0, 0, -1,
      0, 0, -1,
      0, 0, -1,
      0, 0, -1,
      0, 0, -1,
      0, 0, -1
    ], 3)
  );

  const meshData = buildMeshDataFromStlGeometry(geometry, { toCreasedNormals });

  assert.equal(meshData.vertices.length, 18);
  assert.equal(meshData.indices.length, 6);
  assert.deepEqual([...meshData.normals.slice(0, 3)], [0, 0, 1]);
  assert.equal(meshData.has_source_colors, false);
});

// One facet, as three's STLLoader reads it: a normal, three corners, two attribute bytes.
const FACET = [0, 0, 1, 0, 0, 0, 10, 0, 0, 0, 10, 0];

function binaryStl(facets, { stated = facets, header = "", trailing = 0 } = {}) {
  const buffer = new ArrayBuffer(84 + facets * 50 + trailing);
  const view = new DataView(buffer);
  [...header].forEach((character, index) => view.setUint8(index, character.charCodeAt(0)));
  view.setUint32(80, stated, true);
  for (let facet = 0; facet < facets; facet += 1) {
    FACET.forEach((value, index) => view.setFloat32(84 + facet * 50 + index * 4, value, true));
  }
  return buffer;
}

function textStl(facets, before = "") {
  const facet = " facet normal 0 0 1\n  outer loop\n   vertex 0 0 0\n   vertex 10 0 0\n   vertex 0 10 0\n  endloop\n endfacet\n";
  return new TextEncoder().encode(`${before}solid part\n${facet.repeat(facets)}endsolid part\n`).buffer;
}

const triangles = async buffer => (await buildMeshDataFromStlBuffer(buffer)).vertices.length / 9;

test("an STL whose facet count fits its size is read as it was", async () => {
  assert.equal(await triangles(binaryStl(12)), 12);
  assert.equal(await triangles(binaryStl(12, { trailing: 2 })), 12);
  assert.equal(await triangles(binaryStl(12, { header: "solid named by its exporter" })), 12);
  assert.equal(await triangles(textStl(12)), 12);
  assert.equal(await triangles(textStl(12, "﻿")), 12);
});

test("a binary STL whose count is more than it holds has its whole triangles read", async () => {
  // An exporter's count one or many too high, over facets that are all there.
  assert.equal(await triangles(binaryStl(12, { stated: 13 })), 12);
  assert.equal(await triangles(binaryStl(12, { stated: 600_000_000 })), 12);
  assert.equal(await triangles(binaryStl(12, { stated: 0xffffffff, header: "exported by a modeller" })), 12);
  // A download cut short, inside a facet and on a facet's end: the partial facet is left out.
  assert.equal(await triangles(binaryStl(12).slice(0, -20)), 11);
  assert.equal(await triangles(binaryStl(12).slice(0, -50)), 11);
});

test("a binary STL that holds no whole triangle says how many its header counts and how many bytes it has", async () => {
  await assert.rejects(
    buildMeshDataFromStlBuffer(binaryStl(2000).slice(0, 120)),
    { message: "This is not a complete STL file: its header counts 2,000 triangles (100,084 bytes), "
      + "and the file is 120 bytes. It may be cut short, or be another kind of file named .stl." }
  );
});

// What an archive or an image holds: bytes that are not text, in no pattern.
function noise(length) {
  const bytes = new Uint8Array(length);
  let state = 1;
  for (let index = 0; index < length; index += 1) {
    state = (Math.imul(state, 1103515245) + 12345) >>> 0;
    bytes[index] = state >>> 24;
  }
  bytes.set([0x50, 0x4b, 0x03, 0x04]);
  return bytes.buffer;
}

function utf16(text, { bom = true } = {}) {
  const characters = `${bom ? "\ufeff" : ""}${text}`;
  const view = new DataView(new ArrayBuffer(characters.length * 2));
  [...characters].forEach((character, index) => view.setUint16(index * 2, character.charCodeAt(0), true));
  return view.buffer;
}

test("text that does not start with solid is refused as text, before anything is allocated for the count its bytes spell", async () => {
  const page = new TextEncoder().encode(`<!DOCTYPE html>\n<html><body>${"<p>Sign in to download this model.</p>".repeat(40)}</body></html>`).buffer;
  // The four characters at byte 80 read as 1,853,321,060 facets: 66 GB of corners to allocate, for a 1,562-byte file.
  await assert.rejects(
    buildMeshDataFromStlBuffer(page),
    { message: 'This is not an STL file: it is text that does not start with "solid", and an STL in text form starts with that word.' }
  );
  const text = /it is text that does not start with "solid"/u;
  await assert.rejects(buildMeshDataFromStlBuffer(textStl(12, "; exported from a modeller\n")), text);
  await assert.rejects(buildMeshDataFromStlBuffer(new TextEncoder().encode(new TextDecoder().decode(textStl(12)).toUpperCase()).buffer), text);
  await assert.rejects(buildMeshDataFromStlBuffer(utf16(new TextDecoder().decode(textStl(12)))), text);
  await assert.rejects(buildMeshDataFromStlBuffer(utf16(new TextDecoder().decode(textStl(12)), { bom: false })), text);
  await assert.rejects(buildMeshDataFromStlBuffer(new TextEncoder().encode("not a model\n").buffer), text);
});

test("a file that is neither text nor an STL is refused with the count its header states", async () => {
  await assert.rejects(buildMeshDataFromStlBuffer(noise(2000)), /This is not a complete STL file: its header counts [\d,]+ triangles/u);
  await assert.rejects(buildMeshDataFromStlBuffer(new ArrayBuffer(0)), /This is not an STL file: it is 0 bytes, and a binary STL is at least 84\./u);
  await assert.rejects(buildMeshDataFromStlBuffer(new ArrayBuffer(50)), /it is 50 bytes/u);
  await assert.rejects(buildMeshDataFromStlBuffer(new TextEncoder().encode("solid empty\nendsolid empty\n").buffer), /This STL file holds no triangles: it is 27 bytes\./u);
});

test("an STL's text is read when blank lines come before its solid", async () => {
  assert.equal(await triangles(textStl(12, "\n\n      ")), 12);
  assert.equal(await triangles(textStl(12, "﻿\r\n\r\n\t   ")), 12);
});

test("readableStlBuffer hands a readable file over untouched", () => {
  const binary = binaryStl(3);
  const text = textStl(3);
  assert.equal(readableStlBuffer(binary), binary);
  assert.equal(readableStlBuffer(text), text);
});
