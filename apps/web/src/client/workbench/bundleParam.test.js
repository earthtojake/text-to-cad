import assert from "node:assert/strict";
import test from "node:test";

import { readBundleAddress } from "./bundleParam.js";

test("a page's ?bundle= names the folder of the view bundle it shows, on its own origin; no ?bundle= is the engine's page", () => {
  assert.equal(readBundleAddress("https://cad.test/viewer/?bundle=arm.view"), "https://cad.test/viewer/arm.view/");
  assert.equal(readBundleAddress("https://cad.test/viewer/index.html?bundle=/shared/arm.view/#key"), "https://cad.test/shared/arm.view/");
  assert.equal(readBundleAddress("https://cad.test/?bundle=b%2Farm.view%2F%3Fv%3D2"), "https://cad.test/b/arm.view/");
  for (const engine of ["http://127.0.0.1:3245/", "http://127.0.0.1:3245/6f1c2a4e-1b2c-5d3e-8f4a-0123456789ab?token=1800000000.mac"]) {
    assert.equal(readBundleAddress(engine), null);
  }
});

test("a bundle on another origin, or none named, is refused saying why", () => {
  assert.throws(() => readBundleAddress("https://cad.test/?bundle=https://elsewhere.test/arm.view/"), /own origin \(https:\/\/cad\.test\) alone, not https:\/\/elsewhere\.test/);
  assert.throws(() => readBundleAddress("https://cad.test/?bundle=//elsewhere.test/arm.view/"), /not https:\/\/elsewhere\.test/);
  assert.throws(() => readBundleAddress("https://cad.test/?bundle="), /names no view bundle/);
});
