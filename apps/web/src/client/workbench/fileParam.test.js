import assert from "node:assert/strict";
import test from "node:test";

import { pageAddress, readDocumentId, readHomePlace, writeDocumentId } from "./fileParam.js";

const ID = "6f1c2a4e-1b2c-5d3e-8f4a-0123456789ab";

test("a page names its document by id in its path, and every other path is the home", () => {
  assert.equal(readDocumentId(`/${ID}`), ID);
  assert.equal(readDocumentId(`/${ID}/`), ID);
  assert.equal(readDocumentId("/"), null);
  assert.equal(readDocumentId("/Users/me/a.step"), null);
  assert.equal(readDocumentId(`/${ID.toUpperCase()}`), null);
});

test("the URL is /<id> for a document and / for the home, a step pushed for each, its link kept", () => {
  const originalWindow = globalThis.window;
  const calls = [];
  globalThis.window = {
    location: { pathname: "/", search: "?debug=1&token=1800000000.mac", hash: "" },
    history: { pushState: (...args) => calls.push(["push", args[2]]), replaceState: (...args) => calls.push(["replace", args[2]]) },
  };
  try {
    writeDocumentId(ID, { history: "replace" });
    window.location = { pathname: `/${ID}`, search: "?debug=1&token=1800000000.mac", hash: "" };
    writeDocumentId(ID);
    writeDocumentId("");
    // The URL already names the document: nothing is written.
    assert.deepEqual(calls, [
      ["replace", `/${ID}?debug=1&token=1800000000.mac`],
      ["push", "/?debug=1&token=1800000000.mac"],
    ]);
  } finally {
    globalThis.window = originalWindow;
  }
});

test("the home's query names its place: a project's page, Pinned or Standalone, and Recents for anything else", () => {
  assert.deepEqual(readHomePlace(""), { view: "recents" });
  assert.deepEqual(readHomePlace("?view=pinned&token=1.mac"), { view: "pinned" });
  assert.deepEqual(readHomePlace("?view=standalone"), { view: "standalone" });
  assert.deepEqual(readHomePlace("?token=1.mac&project=p1"), { view: "project", project: "p1" });
  // A view the home does not have, and an old link's query, are Recents.
  assert.deepEqual(readHomePlace("?view=trash&file=a.step"), { view: "recents" });
});

test("each place and each document has its own address, beside what the page's address carries", () => {
  const carried = { search: "?view=pinned&debug=1&token=1800000000.mac", hash: "" };
  assert.equal(pageAddress({}, carried), "/?debug=1&token=1800000000.mac");
  assert.equal(pageAddress({ place: { view: "recents" } }, carried), "/?debug=1&token=1800000000.mac");
  assert.equal(pageAddress({ place: { view: "standalone" } }, carried), "/?view=standalone&debug=1&token=1800000000.mac");
  assert.equal(pageAddress({ place: { view: "project", project: "p 1" } }, carried), "/?project=p+1&debug=1&token=1800000000.mac");
  // A document's page names no place, whatever the address it is linked from does.
  assert.equal(pageAddress({ id: ID, place: { view: "pinned" } }, { search: "?project=p1&token=1800000000.mac", hash: "" }), `/${ID}?token=1800000000.mac`);
  assert.equal(pageAddress({ place: { view: "pinned" } }, { search: "", hash: "" }), "/?view=pinned");
  // What it writes is what it reads.
  assert.deepEqual(readHomePlace(pageAddress({ place: { view: "project", project: "p 1" } }, carried).slice(1)), { view: "project", project: "p 1" });
});

test("a place on the home is a step in the history, and leaving for a document drops it from the address", () => {
  const originalWindow = globalThis.window;
  const calls = [];
  const at = (pathname, search) => { window.location = { pathname, search, hash: "" }; };
  globalThis.window = { location: { pathname: "/", search: "?token=1.mac", hash: "" },
    history: { pushState: (...args) => calls.push(["push", args[2]]), replaceState: (...args) => calls.push(["replace", args[2]]) } };
  try {
    writeDocumentId("", { place: { view: "project", project: "p1" } });
    at("/", "?project=p1&token=1.mac");
    writeDocumentId("", { place: { view: "project", project: "p1" } });  // already there: nothing is written
    writeDocumentId("", { place: { view: "pinned" }, history: "replace" });
    at("/", "?view=pinned&token=1.mac");
    writeDocumentId(ID);
    at(`/${ID}`, "?token=1.mac");
    writeDocumentId("");
    assert.deepEqual(calls, [["push", "/?project=p1&token=1.mac"], ["replace", "/?view=pinned&token=1.mac"], ["push", `/${ID}?token=1.mac`], ["push", "/?token=1.mac"]]);
  } finally {
    globalThis.window = originalWindow;
  }
});
