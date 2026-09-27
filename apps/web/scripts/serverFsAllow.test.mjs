import assert from "node:assert/strict";
import test from "node:test";

import { resolveServerFsAllow } from "./serverFsAllow.mjs";

test("server fs allow list includes the real path behind a symlinked package root", () => {
  // A checkout that reaches @hardcore/core through a link: the real path is allowed too.
  const realpath = (value) =>
    value === "/repo/viewer/packages/core/src" ? "/repo/packages/core/src" : value;
  const allow = resolveServerFsAllow(["/repo/viewer", "/repo/viewer/packages/core/src"], { realpath });
  assert.deepEqual(allow, [
    "/repo/viewer",
    "/repo/viewer/packages/core/src",
    "/repo/packages/core/src",
  ]);
});

test("server fs allow list dedupes when the package root is not a symlink", () => {
  const allow = resolveServerFsAllow(["/repo/viewer", "/repo/viewer/packages/core/src"], {
    realpath: (value) => value,
  });
  assert.deepEqual(allow, ["/repo/viewer", "/repo/viewer/packages/core/src"]);
});

test("server fs allow list keeps roots whose real path cannot be read", () => {
  const allow = resolveServerFsAllow(["/repo/viewer"], {
    realpath: () => {
      throw new Error("ENOENT");
    },
  });
  assert.deepEqual(allow, ["/repo/viewer"]);
});

test("server fs allow list skips empty entries and works without a realpath resolver", () => {
  assert.deepEqual(resolveServerFsAllow(["/repo/viewer", "", null]), ["/repo/viewer"]);
  assert.deepEqual(resolveServerFsAllow([]), []);
});
