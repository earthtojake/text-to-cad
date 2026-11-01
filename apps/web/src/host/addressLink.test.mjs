import assert from "node:assert/strict";
import test from "node:test";
import { JSDOM } from "jsdom";
import { LINK_REFRESH_SECONDS, keepAddressLink } from "./addressLink.js";

const NOW = 1_800_000_000;
const PAGE = "http://127.0.0.1:3245/6f1c2a4e-1b2c-5d3e-8f4a-000000000001";

/** A page at `url`, its links asked of a server that answers `fresh` and counts the asks. */
async function opened(url) {
  const dom = new JSDOM("<div></div>", { url });
  const asked = [];
  const fresh = `${NOW + 86_400}.fresh`;
  const stop = keepAddressLink({ page: dom.window, now: () => NOW,
    fetchLink: async () => { asked.push(dom.window.location.href); return { link: fresh, expires: NOW + 86_400 }; } });
  await stop.started;
  return { dom, asked, fresh, stop };
}

test("a page loaded without a link (a reload its cookie admitted) writes a fresh one into its address", async () => {
  const { dom, asked, fresh, stop } = await opened(`${PAGE}?view=top#part`);
  try {
    assert.equal(asked.length, 1);
    const { pathname, search, hash } = dom.window.location;
    assert.equal(pathname, "/6f1c2a4e-1b2c-5d3e-8f4a-000000000001", "the same page");
    assert.equal(new URLSearchParams(search).get("token"), fresh);
    assert.equal(new URLSearchParams(search).get("view"), "top", "the rest of the query kept");
    assert.equal(hash, "#part");
    assert.equal(dom.window.history.length, 1, "written in place, no new history entry");
  } finally { stop(); dom.window.close(); }
});

test("a page whose link has more than half a day left keeps it, also when it is shown again", async () => {
  const link = `${NOW + LINK_REFRESH_SECONDS + 60}.kept`;
  const { dom, asked, stop } = await opened(`${PAGE}?token=${link}`);
  try {
    dom.window.dispatchEvent(new dom.window.Event("focus"));
    dom.window.document.dispatchEvent(new dom.window.Event("visibilitychange"));
    await new Promise(resolve => setImmediate(resolve));
    assert.deepEqual(asked, [], "nothing asked");
    assert.equal(new URLSearchParams(dom.window.location.search).get("token"), link);
  } finally { stop(); dom.window.close(); }
});

test("a link near its expiry is replaced, on load and when the page is shown again", async () => {
  const { dom, asked, fresh, stop } = await opened(`${PAGE}?token=${NOW + 3600}.old`);
  try {
    assert.equal(asked.length, 1);
    assert.equal(new URLSearchParams(dom.window.location.search).get("token"), fresh);
    // The home, reached later with a link that has aged past the threshold, is refreshed when shown.
    dom.window.history.replaceState(null, "", `/?token=${NOW + 60}.aging`);
    dom.window.document.dispatchEvent(new dom.window.Event("visibilitychange"));
    await new Promise(resolve => setImmediate(resolve));
    assert.equal(asked.length, 2);
    assert.equal(dom.window.location.pathname, "/");
    assert.equal(new URLSearchParams(dom.window.location.search).get("token"), fresh);
  } finally { stop(); dom.window.close(); }
});
