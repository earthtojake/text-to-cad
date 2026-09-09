import assert from "node:assert/strict";
import test from "node:test";

import { buildSidebarDirectoryTree } from "../workbench/sidebar.js";
import { catalogDirectoryListing, createCatalogFileSource } from "./catalogFileSource.js";

/**
 * The standalone viewer's answer to "what is in this directory": a walk of
 * the tree the client already built from its catalog, in the crumb path
 * space, with no request in it.
 */

const entries = [
  { file: "assemblies/arm/base.step", kind: "step" },
  { file: "assemblies/arm/forearm.step", kind: "step" },
  { file: "assemblies/wrist.step", kind: "step" },
  { file: "drawings/plate.dxf", kind: "dxf" },
  { file: "top.step", kind: "step" }
];

const tree = buildSidebarDirectoryTree(entries);

test("the root lists its folders and its files, in the crumb path space", () => {
  const listing = catalogDirectoryListing(tree, "");
  // Root-relative paths throughout: exactly what `buildCrumbs` splits and
  // what a directory id extends, so a crumb's `menu` looks its own entries up.
  assert.deepEqual(
    listing.map((item) => [item.kind, item.path, item.name]),
    [
      ["directory", "assemblies", "assemblies"],
      ["directory", "drawings", "drawings"],
      ["file", "top.step", "top.step"]
    ]
  );
});

test("a nested directory lists its own children", () => {
  assert.deepEqual(
    catalogDirectoryListing(tree, "assemblies").map((item) => [item.kind, item.path, item.name]),
    [
      // The path is the full directory id; the name is the one segment drawn.
      ["directory", "assemblies/arm", "arm"],
      ["file", "assemblies/wrist.step", "wrist.step"]
    ]
  );
  assert.deepEqual(
    catalogDirectoryListing(tree, "assemblies/arm").map((item) => item.path),
    ["assemblies/arm/base.step", "assemblies/arm/forearm.step"]
  );
});

test("a file entry carries the catalog entry it came from", () => {
  // The standalone selects by the entry's key; handing the entry back through
  // `onOpen` is how the breadcrumb avoids looking it up again by path.
  const listing = catalogDirectoryListing(tree, "assemblies/arm");
  assert.equal(listing[0].value, entries[0]);
  // A folder names no entry.
  assert.equal(catalogDirectoryListing(tree, "")[0].value, undefined);
});

test("no tree yet is reading; an unknown directory is empty", () => {
  // The catalog's first poll has not landed: the menu says "Reading…".
  assert.equal(catalogDirectoryListing(null, ""), null);
  // A folder whose files have gone since the tree was built is empty, which
  // is honest — it is not a failure and it is not still loading.
  assert.deepEqual(catalogDirectoryListing(tree, "nowhere"), []);
});

test("the source exposes the listing as a hook and keeps the host's slots", () => {
  const wrapCrumb = ({ children }) => children;
  const source = createCatalogFileSource({ directoryTree: tree, slots: { wrapCrumb } });
  assert.equal(source.wrapCrumb, wrapCrumb);
  assert.deepEqual(
    source.useListing("drawings").map((item) => item.path),
    ["drawings/plate.dxf"]
  );
});
