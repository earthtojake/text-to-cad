import assert from "node:assert/strict";
import path from "node:path";
import test from "node:test";

import { resolveWorkspaceRoot } from "./workspaceRoot.mjs";

test("resolveWorkspaceRoot ignores deprecated local filesystem workspace env var", () => {
  assert.equal(
    resolveWorkspaceRoot({
      env: { VIEWER_LOCAL_WORKSPACE_ROOT: "models-workspace" },
      cwd: "/tmp",
    }),
    path.resolve("/tmp")
  );
});
