// The worker client's cache identity rule: only a content-addressed component
// surf (components/<cid>.surf) may key the shared tessellation cache — an
// arbitrary .surf path has no stable identity and caching it by name would
// collide across models.
import assert from "node:assert/strict";
import test from "node:test";

import { cidFromSurfUrl, loadSurfComponentInWorker } from "./surfWorkerClient.js";

test("cidFromSurfUrl accepts only components/<cid>.surf", () => {
  assert.equal(
    cidFromSurfUrl("/__cad/models/__cadgen__/models/x.step/components/abc123.surf"),
    "abc123",
  );
  assert.equal(cidFromSurfUrl("http://h/pkg/components/deadbeef.surf?v=1#frag"), "deadbeef");
  assert.equal(cidFromSurfUrl("/pkg/components/upper%2Bcase.surf"), "upper+case");
  assert.equal(cidFromSurfUrl("/pkg/other/abc.surf"), "", "non-components dir");
  assert.equal(cidFromSurfUrl("/components/abc.notsurf"), "", "wrong extension");
  assert.equal(cidFromSurfUrl("abc.surf"), "", "no components parent");
  assert.equal(cidFromSurfUrl(""), "");
});

test("cidFromSurfUrl reads the viewer's query-form asset URLs", () => {
  // The viewer serves package components through /__cad/asset?file=<abs path>.
  // The first release parsed only path-form URLs, which disabled the entire
  // shared-cache integration in the real client (no reads, no write-backs).
  assert.equal(
    cidFromSurfUrl(
      "/__cad/asset?file=%2Fabs%2Fmodels%2F__cadgen__%2Fmodels%2Fx.step%2Fcomponents%2Fc384534572a08e23.surf&v=abc123",
    ),
    "c384534572a08e23",
  );
  assert.equal(
    cidFromSurfUrl("/__cad/asset?v=1&file=/plain/pkg/components/deadbeef.surf"),
    "deadbeef",
    "unencoded file param, param order independent",
  );
  assert.equal(
    cidFromSurfUrl("/__cad/asset?file=/pkg/components/abc.surf#frag"),
    "abc",
    "fragment stripped before query parse",
  );
  assert.equal(
    cidFromSurfUrl("/__cad/asset?file=/pkg/other/abc.surf"),
    "",
    "query form still requires a components/ parent",
  );
  assert.equal(
    cidFromSurfUrl("/__cad/asset?file=/pkg/components/assembly.json"),
    "",
    "query form still requires the .surf extension",
  );
  assert.equal(cidFromSurfUrl("/__cad/asset?other=/pkg/components/abc.surf"), "", "no file param");
});

test("loadSurfComponentInWorker returns null where Workers do not exist (node)", () => {
  assert.equal(loadSurfComponentInWorker("/pkg/components/abc.surf"), null);
});
