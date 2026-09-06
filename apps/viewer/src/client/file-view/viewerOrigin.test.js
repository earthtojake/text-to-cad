// Every URL the file-view surface builds, at both origins it is ever built for:
// "" (the standalone viewer, served BY its own backend) and an absolute origin
// (a host embedding <CadFileView> against another `cadgen viewer`).
//
// The "" column is the regression guard that matters most: it is the shipping
// viewer, and every one of these must stay byte-identical to the root-relative
// URL that shipped before the origin existed.
import assert from "node:assert/strict";
import test from "node:test";

import {
  applyViewerOriginToEntries,
  applyViewerOriginToEntry,
  isAbsoluteViewerUrl,
  normalizeViewerOrigin,
  viewerOriginUrl,
} from "./viewerOrigin.js";
import { cadApiUrl } from "../workbench/cadManifestStore.js";
import { resolvePackageAssetUrl } from "../components/workbench/hooks/packageAssetUrl.js";

const REMOTE = "http://127.0.0.1:3250";

test("normalizeViewerOrigin keeps the same-origin default empty", () => {
  assert.equal(normalizeViewerOrigin(undefined), "");
  assert.equal(normalizeViewerOrigin(""), "");
  assert.equal(normalizeViewerOrigin("   "), "");
  assert.equal(normalizeViewerOrigin(REMOTE), REMOTE);
  assert.equal(normalizeViewerOrigin(`${REMOTE}/`), REMOTE);
  assert.equal(normalizeViewerOrigin(`${REMOTE}//`), REMOTE);
});

test("viewerOriginUrl leaves root-relative URLs alone at the same origin", () => {
  assert.equal(viewerOriginUrl("", "/__cad/catalog"), "/__cad/catalog");
  assert.equal(viewerOriginUrl("", "/__tess_cache/batch"), "/__tess_cache/batch");
});

test("viewerOriginUrl prefixes a remote origin exactly once", () => {
  assert.equal(viewerOriginUrl(REMOTE, "/__cad/catalog"), `${REMOTE}/__cad/catalog`);
  assert.equal(viewerOriginUrl(REMOTE, "__cad/catalog"), `${REMOTE}/__cad/catalog`);
  // Applying it twice is a no-op: the URL is already absolute.
  assert.equal(
    viewerOriginUrl(REMOTE, viewerOriginUrl(REMOTE, "/__cad/catalog")),
    `${REMOTE}/__cad/catalog`,
  );
  assert.equal(viewerOriginUrl(REMOTE, ""), "");
});

test("isAbsoluteViewerUrl separates the two URL shapes", () => {
  assert.equal(isAbsoluteViewerUrl("/__cad/asset?file=x"), false);
  assert.equal(isAbsoluteViewerUrl(`${REMOTE}/__cad/asset?file=x`), true);
  assert.equal(isAbsoluteViewerUrl("https://example.test/a"), true);
  assert.equal(isAbsoluteViewerUrl(""), false);
});

test("cadApiUrl builds the catalog and artifact routes for both origins", () => {
  assert.equal(cadApiUrl("/__cad/catalog"), "/__cad/catalog");
  assert.equal(cadApiUrl("/__cad/catalog", { file: "STEP/arm.step" }), "/__cad/catalog?file=STEP%2Farm.step");
  assert.equal(
    cadApiUrl("/__cad/artifact", { params: { file: "STEP/arm.step", force: "1" } }),
    "/__cad/artifact?file=STEP%2Farm.step&force=1",
  );
  assert.equal(cadApiUrl("/__cad/catalog", { origin: REMOTE }), `${REMOTE}/__cad/catalog`);
  assert.equal(
    cadApiUrl("/__cad/catalog", { origin: `${REMOTE}/`, file: "STEP/arm.step" }),
    `${REMOTE}/__cad/catalog?file=STEP%2Farm.step`,
  );
  assert.equal(
    cadApiUrl("/__cad/artifact", { origin: REMOTE, params: { file: "STEP/arm.step" } }),
    `${REMOTE}/__cad/artifact?file=STEP%2Farm.step`,
  );
  assert.equal(cadApiUrl("/__cad/server", { origin: REMOTE }), `${REMOTE}/__cad/server`);
});

test("catalog entries are rebased onto the origin, and only their URL fields", () => {
  const entry = {
    file: "/abs/models/arm.step",
    kind: "step",
    hash: "h1",
    url: "/__cad/asset?file=%2Fabs%2Fmodels%2Farm.step&v=h1",
    poseUrl: "/__cad/asset?file=%2Fabs%2Fmodels%2Farm.step.json",
    renderModuleUrl: "/__cad/asset?file=%2Fabs%2Fmodels%2Farm.step.js",
    relations: {
      glb: { url: "/__cad/asset?file=%2Fabs%2Fpkg&v=h2", hash: "h2", bytes: 3 },
      none: { hash: "h3" },
    },
  };

  assert.equal(applyViewerOriginToEntry(entry, ""), entry, "same origin returns the entry untouched");

  const rebased = applyViewerOriginToEntry(entry, REMOTE);
  assert.notEqual(rebased, entry, "a rebase never mutates the catalog entry");
  assert.equal(rebased.url, `${REMOTE}/__cad/asset?file=%2Fabs%2Fmodels%2Farm.step&v=h1`);
  assert.equal(rebased.poseUrl, `${REMOTE}/__cad/asset?file=%2Fabs%2Fmodels%2Farm.step.json`);
  assert.equal(rebased.renderModuleUrl, `${REMOTE}/__cad/asset?file=%2Fabs%2Fmodels%2Farm.step.js`);
  assert.equal(rebased.relations.glb.url, `${REMOTE}/__cad/asset?file=%2Fabs%2Fpkg&v=h2`);
  assert.equal(rebased.relations.glb.hash, "h2");
  assert.deepEqual(rebased.relations.none, { hash: "h3" });
  // `file` is a path on the SERVER's disk, not a URL; rebasing it would break every
  // catalog key the client builds from it.
  assert.equal(rebased.file, entry.file);
  assert.equal(rebased.hash, "h1");

  assert.equal(applyViewerOriginToEntries([entry], "")[0], entry);
  assert.equal(applyViewerOriginToEntries([entry], REMOTE)[0].url, rebased.url);
  assert.deepEqual(applyViewerOriginToEntries(null, REMOTE), []);
});

test("package sub-asset URLs keep the shape of the package URL they came from", () => {
  const localPackage = "/__cad/asset?file=%2Fabs%2Fpkg.step&v=abc";
  assert.equal(
    resolvePackageAssetUrl(localPackage, "assembly.json"),
    "/__cad/asset?file=%2Fabs%2Fpkg.step%2Fassembly.json&v=abc",
  );
  assert.equal(
    resolvePackageAssetUrl(`${REMOTE}${localPackage}`, "assembly.json"),
    `${REMOTE}/__cad/asset?file=%2Fabs%2Fpkg.step%2Fassembly.json&v=abc`,
  );
  assert.equal(
    resolvePackageAssetUrl(`${REMOTE}${localPackage}`, "components/7e4f.glb"),
    `${REMOTE}/__cad/asset?file=%2Fabs%2Fpkg.step%2Fcomponents%2F7e4f.glb&v=abc`,
  );
});
