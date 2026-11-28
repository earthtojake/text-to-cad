import assert from "node:assert/strict";
import test from "node:test";

import { createNewTabOpener } from "./newTab.js";

const ID = "6f1c2a4e-1b2c-5d3e-8f4a-0123456789ab";
// A page that records what it opens: each tab its address, its features and what became of it.
function page() {
  const tabs = [];
  return { tabs, location: { href: "http://cad.local/?view=pinned&token=1.mac" },
    open(address, name, features) {
      const tab = { address, name, features, opener: "page", closed: false, close() { tab.closed = true; }, location: { replace(next) { tab.address = next; } } };
      tabs.push(tab);
      return features === "noopener" ? null : tab;
    } };
}
const hrefOf = target => "home" in target ? `/?project=${target.home.project}&token=1.mac` : /^[0-9a-f-]{36}$/.test(target.document) ? `/${target.document}?token=1.mac` : null;

test("a target with an address opens at it in a new tab, cut off from this page", async () => {
  const browser = page();
  const open = createNewTabOpener({ hrefOf, resolve: async () => { throw new Error("not asked"); }, page: browser });
  await open({ document: ID });
  await open({ home: { view: "project", project: "p1" } });
  assert.deepEqual(browser.tabs.map(tab => [tab.address, tab.name, tab.features]), [
    [`http://cad.local/${ID}?token=1.mac`, "_blank", "noopener"], ["http://cad.local/?project=p1&token=1.mac", "_blank", "noopener"]]);
});

test("a file named by its path gets its tab at once, and its page once the server names its document", async () => {
  const browser = page();
  let answer;
  const open = createNewTabOpener({ hrefOf, resolve: path => new Promise(resolve => { answer = () => resolve(path === "/work/a.step" ? ID : ""); }), page: browser });
  const opening = open({ document: "/work/a.step" });
  // Opened inside the press, empty, before the server has answered.
  assert.deepEqual(browser.tabs.map(tab => [tab.address, tab.closed]), [["", false]]);
  answer();
  await opening;
  assert.deepEqual(browser.tabs.map(tab => [tab.address, tab.opener, tab.closed]), [[`http://cad.local/${ID}?token=1.mac`, null, false]]);
});

test("a file that cannot be resolved closes the tab it opened, and says why", async () => {
  const browser = page();
  const open = createNewTabOpener({ hrefOf, resolve: async () => { throw new Error("File does not exist: /work/gone.step"); }, page: browser });
  await assert.rejects(open({ document: "/work/gone.step" }), /File does not exist/);
  assert.deepEqual(browser.tabs.map(tab => tab.closed), [true]);
});
