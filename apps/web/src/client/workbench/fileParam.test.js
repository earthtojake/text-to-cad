import assert from "node:assert/strict";
import test from "node:test";

import { readDocumentId, writeDocumentId } from "./fileParam.js";

const ID = "6f1c2a4e-1b2c-5d3e-8f4a-0123456789ab";

test("a page names its document by id in its path, and every other path is the home", () => {
  assert.equal(readDocumentId(`/${ID}`), ID);
  assert.equal(readDocumentId(`/${ID}/`), ID);
  assert.equal(readDocumentId("/"), null);
  assert.equal(readDocumentId("/Users/me/a.step"), null);
  assert.equal(readDocumentId(`/${ID.toUpperCase()}`), null);
});

test("the URL is /<id> for a document and / for the home, a step pushed for each", () => {
  const originalWindow = globalThis.window;
  const calls = [];
  globalThis.window = {
    location: { pathname: "/", search: "?debug=1", hash: "" },
    history: { pushState: (...args) => calls.push(["push", args[2]]), replaceState: (...args) => calls.push(["replace", args[2]]) },
  };
  try {
    writeDocumentId(ID, { history: "replace" });
    window.location = { pathname: `/${ID}`, search: "?debug=1", hash: "" };
    writeDocumentId(ID);
    writeDocumentId("");
    // The URL already names the document: nothing is written.
    assert.deepEqual(calls, [
      ["replace", `/${ID}?debug=1`],
      ["push", "/?debug=1"],
    ]);
  } finally {
    globalThis.window = originalWindow;
  }
});
