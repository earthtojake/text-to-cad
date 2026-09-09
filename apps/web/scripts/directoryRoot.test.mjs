import assert from "node:assert/strict";
import path from "node:path";
import test from "node:test";

import { resolveDirectoryRoot } from "./directoryRoot.mjs";

test("resolveDirectoryRoot ignores deprecated local filesystem directory env var", () => {
  assert.equal(
    resolveDirectoryRoot({
      env: { VIEWER_LOCAL_WORKSPACE_ROOT: "models-directory" },
      cwd: "/tmp",
    }),
    path.resolve("/tmp")
  );
});
