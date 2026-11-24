import assert from "node:assert/strict";
import test from "node:test";

import { browserLanguage, LANGUAGE_KEY } from "./browserLanguage.js";

function storage() {
  const held = new Map();
  return { held, getItem: key => (held.has(key) ? held.get(key) : null), setItem: (key, value) => held.set(key, String(value)), removeItem: key => held.delete(key) };
}

test("the person's language, where no server keeps it, is kept in the browser: read, chosen and cleared", async () => {
  const kept = storage();
  const language = browserLanguage(kept);
  assert.deepEqual(await language(), { locale: null });
  assert.deepEqual(await language("ja"), { locale: "ja" });
  assert.equal(kept.held.get(LANGUAGE_KEY), "ja");
  // Another page of this viewer in the same browser reads the same choice.
  assert.deepEqual(await browserLanguage(kept)(), { locale: "ja" });
  assert.deepEqual(await language(null), { locale: null });
  assert.equal(kept.held.has(LANGUAGE_KEY), false);
});
