import assert from "node:assert/strict";
import test from "node:test";

import { readFileParam, resolveFileParam, writeFileParam } from "./fileParam.js";

test("a link names its file absolutely; a developer's relative one resolves against where the viewer started", () => {
  assert.equal(readFileParam("?file=/Users/me/arm%20parts/link%20%232.step"), "/Users/me/arm parts/link #2.step");
  assert.equal(readFileParam(""), null);
  assert.equal(resolveFileParam("/Users/me/a.step", "/work"), "/Users/me/a.step");
  assert.equal(resolveFileParam("parts/../STEP/./a.step", "/work/models/"), "/work/models/STEP/a.step");
  assert.equal(resolveFileParam("C:\\work\\a.step", "/x"), "C:/work/a.step");
  assert.equal(resolveFileParam("a.step", "C:\\work"), "C:/work/a.step");
  assert.equal(resolveFileParam("", "/work"), "");
});

test("the URL names the file readably, pushes a step for a new file, and drops ?file= for the home", () => {
  const originalWindow = globalThis.window;
  const calls = [];
  globalThis.window = {
    location: { pathname: "/", search: "?file=/m/a.step&debug=1", hash: "" },
    history: { pushState: (...args) => calls.push(["push", args[2]]), replaceState: (...args) => calls.push(["replace", args[2]]) },
  };
  try {
    writeFileParam("/m/a.step", { history: "replace" });
    writeFileParam("/m/arm parts/b+c #2.step");
    writeFileParam("");
    // The URL already names the file: nothing is written.
    assert.deepEqual(calls, [
      ["push", "/?file=/m/arm%20parts/b%2Bc%20%232.step&debug=1"],
      ["push", "/?debug=1"],
    ]);
  } finally {
    globalThis.window = originalWindow;
  }
});
