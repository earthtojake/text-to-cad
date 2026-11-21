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

test("a binary STL cut short says how many triangles its header counts and how many bytes it has", async () => {
  await assert.rejects(
    buildMeshDataFromStlBuffer(binaryStl(2000).slice(0, -100)),
    { message: "This is not a complete STL file: its header counts 2,000 triangles (100,084 bytes), "
      + "and the file is 99,984 bytes. It may be cut short, or be another kind of file named .stl." }
  );
  await assert.rejects(buildMeshDataFromStlBuffer(binaryStl(12, { stated: 0xffffffff })), /counts 4,294,967,295 triangles/u);
});

test("a file that is no STL is refused before anything is allocated for the count its bytes spell", async () => {
  const page = new TextEncoder().encode(`<!DOCTYPE html>\n<html><body>${"<p>Sign in to download this model.</p>".repeat(40)}</body></html>`).buffer;
  // The four characters at byte 80 read as 1,853,321,060 facets: 66 GB of corners to allocate, for a 1,562-byte file.
  await assert.rejects(
    buildMeshDataFromStlBuffer(page),
    { message: "This is not a complete STL file: its header counts 1,853,321,060 triangles (92,666,053,084 bytes), "
      + "and the file is 1,562 bytes. It may be cut short, or be another kind of file named .stl." }
  );
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
