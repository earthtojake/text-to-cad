// Every URL the file-view surface builds, at both origins it is ever built for:
// "" (the standalone viewer, served BY its own backend) and an absolute origin
// (a host embedding <CadFileView> against another `cad viewer`).
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
} from "./origin.js";
import { cadApiUrl } from "./client.js";

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
  assert.equal(viewerOriginUrl("", "/api/v1/documents"), "/api/v1/documents");
  assert.equal(viewerOriginUrl("", "/api/v1/look"), "/api/v1/look");
});

test("viewerOriginUrl prefixes a remote origin exactly once", () => {
  assert.equal(viewerOriginUrl(REMOTE, "/api/v1/documents"), `${REMOTE}/api/v1/documents`);
  assert.equal(viewerOriginUrl(REMOTE, "api/v1/documents"), `${REMOTE}/api/v1/documents`);
  // Applying it twice is a no-op: the URL is already absolute.
  assert.equal(
    viewerOriginUrl(REMOTE, viewerOriginUrl(REMOTE, "/api/v1/documents")),
    `${REMOTE}/api/v1/documents`,
  );
  assert.equal(viewerOriginUrl(REMOTE, ""), "");
});

test("isAbsoluteViewerUrl separates the two URL shapes", () => {
  assert.equal(isAbsoluteViewerUrl("/api/v1/local/files?path=x"), false);
  assert.equal(isAbsoluteViewerUrl(`${REMOTE}/api/v1/local/files?path=x`), true);
  assert.equal(isAbsoluteViewerUrl("https://example.test/a"), true);
  assert.equal(isAbsoluteViewerUrl(""), false);
});

test("cadApiUrl builds the catalog and artifact routes for both origins", () => {
  assert.equal(cadApiUrl("/api/v1/documents"), "/api/v1/documents");
  assert.equal(cadApiUrl("/api/v1/documents", { file: "STEP/arm.step" }), "/api/v1/documents?file=STEP%2Farm.step");
  assert.equal(
    cadApiUrl("/api/v1/artifact", { params: { file: "STEP/arm.step", force: "1" } }),
    "/api/v1/artifact?file=STEP%2Farm.step&force=1",
  );
  assert.equal(cadApiUrl("/api/v1/documents", { origin: REMOTE }), `${REMOTE}/api/v1/documents`);
  assert.equal(
    cadApiUrl("/api/v1/documents", { origin: `${REMOTE}/`, file: "STEP/arm.step" }),
    `${REMOTE}/api/v1/documents?file=STEP%2Farm.step`,
  );
  assert.equal(
    cadApiUrl("/api/v1/artifact", { origin: REMOTE, params: { file: "STEP/arm.step" } }),
    `${REMOTE}/api/v1/artifact?file=STEP%2Farm.step`,
  );
  assert.equal(cadApiUrl("/api/v1/server", { origin: REMOTE }), `${REMOTE}/api/v1/server`);
});

test("catalog entries are rebased onto the origin, and only their URL fields", () => {
  const entry = {
    file: "/abs/models/arm.step",
    kind: "step",
    hash: "h1",
    url: "/api/v1/local/files?path=%2Fabs%2Fmodels%2Farm.step&v=h1",
    poseUrl: "/api/v1/local/files?path=%2Fabs%2Fmodels%2Farm.step.json",
    relations: {
      glb: { url: "/api/v1/local/files?path=%2Fabs%2Fpkg&v=h2", hash: "h2", bytes: 3 },
      none: { hash: "h3" },
    },
  };

  assert.equal(applyViewerOriginToEntry(entry, ""), entry, "same origin returns the entry untouched");

  const rebased = applyViewerOriginToEntry(entry, REMOTE);
  assert.notEqual(rebased, entry, "a rebase never mutates the catalog entry");
  assert.equal(rebased.url, `${REMOTE}/api/v1/local/files?path=%2Fabs%2Fmodels%2Farm.step&v=h1`);
  assert.equal(rebased.poseUrl, `${REMOTE}/api/v1/local/files?path=%2Fabs%2Fmodels%2Farm.step.json`);
  assert.equal(rebased.relations.glb.url, `${REMOTE}/api/v1/local/files?path=%2Fabs%2Fpkg&v=h2`);
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
