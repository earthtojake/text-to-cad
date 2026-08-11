import assert from "node:assert/strict";
import test from "node:test";

import { assertNoDeprecatedLocalRootEnv } from "./viewerEnv.mjs";

test("viewer env rejects deprecated local root environment variables", () => {
  assert.doesNotThrow(() => assertNoDeprecatedLocalRootEnv({}));
  assert.throws(
    () => assertNoDeprecatedLocalRootEnv({ VIEWER_LOCAL_ROOT_DIR: "models" }),
    /no longer supported/
  );
  assert.throws(
    () => assertNoDeprecatedLocalRootEnv({ VIEWER_LOCAL_WORKSPACE_ROOT: "/tmp/directory" }),
    /no longer supported/
  );
});
