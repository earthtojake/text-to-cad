import assert from "node:assert/strict";
import test from "node:test";

import { createLatestAsyncCommitGuard } from "./latestAsyncCommitGuard.js";

test("latest async commit guard rejects stale request tokens", () => {
  const guard = createLatestAsyncCommitGuard();
  const first = guard.begin();
  const second = guard.begin();

  assert.equal(guard.isLatest(first), false);
  assert.equal(guard.isLatest(second), true);
});

test("latest async commit guard invalidates cleared requests", () => {
  const guard = createLatestAsyncCommitGuard();
  const request = guard.begin();

  guard.clear();

  assert.equal(guard.isLatest(request), false);
});
