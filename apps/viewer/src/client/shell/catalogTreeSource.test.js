import assert from "node:assert/strict";
import test from "node:test";

import { buildSidebarDirectoryTree } from "../workbench/sidebar.js";
import { catalogTreeListings, catalogTreePaths } from "./catalogTreeSource.js";

/**
 * The standalone viewer's file tree reads the catalog rather than a directory.
 *
 * The rows, the glyphs and the keyboard are the desktop app's component; what
 * differs is the CONTENT, and this is where that difference is written down:
 * the CAD files the served directory holds, and the directories containing
 * them.
 */

const ENTRIES = [
  { file: "/served/assemblies/arm.step", rootRelativeFile: "assemblies/arm.step" },
  { file: "/served/parts/servo/horn.step", rootRelativeFile: "parts/servo/horn.step" },
  { file: "/served/parts/bracket.dxf", rootRelativeFile: "parts/bracket.dxf" },
  { file: "/served/top.stl", rootRelativeFile: "top.stl" }
];

const TREE = buildSidebarDirectoryTree(ENTRIES);

test("every directory in the catalog is a listing, keyed by its id", () => {
  const listings = catalogTreeListings(TREE);
  assert.deepEqual(Object.keys(listings).sort(), [
    "",
    "assemblies",
    "parts",
    "parts/servo"
  ]);
});

test("a listing is folders first, then files, in the crumb path space", () => {
  const listings = catalogTreeListings(TREE);
  assert.deepEqual(listings[""], [
    { path: "assemblies", name: "assemblies", kind: "directory" },
    { path: "parts", name: "parts", kind: "directory" },
    { path: "top.stl", name: "top.stl", kind: "file" }
  ]);
  assert.deepEqual(listings.parts, [
    { path: "parts/servo", name: "servo", kind: "directory" },
    { path: "parts/bracket.dxf", name: "bracket.dxf", kind: "file" }
  ]);
});

test("a catalog that has not arrived is no listings at all, which reads as loading", () => {
  // The tree shows "Reading…" while the root's listing is absent, so a null
  // tree must not answer with an empty root.
  assert.deepEqual(catalogTreeListings(null), {});
  assert.equal(catalogTreeListings(null)[""], undefined);
});

test("the filter's corpus is every file path, flat and sorted", () => {
  assert.deepEqual(catalogTreePaths(TREE), [
    "assemblies/arm.step",
    "parts/bracket.dxf",
    "parts/servo/horn.step",
    "top.stl"
  ]);
  assert.deepEqual(catalogTreePaths(null), []);
});

test("only files the viewer can open are in it — the honest web subset", () => {
  // The catalog holds CAD files and nothing else, so a `.py` beside a `.step`
  // is not in the tree. That is the one place the two apps' trees differ in
  // content, and it differs because the backend has no directory to list.
  const paths = catalogTreePaths(TREE);
  assert.ok(paths.every((path) => /\.(step|stp|stl|3mf|glb|dxf|urdf|srdf|sdf)$/u.test(path)));
});
