import assert from "node:assert/strict";
import { test } from "node:test";

import en from "../i18n/locales/en.js";
import ja from "../i18n/locales/ja.js";
import ko from "../i18n/locales/ko.js";
import zhCN from "../i18n/locales/zh-CN.js";
import zhTW from "../i18n/locales/zh-TW.js";
import { MAX_ITEMS, WHATS_NEW, whatsNewEntry, whatsNewNotes } from "./notes.js";

const TABLES = { en, ja, ko, "zh-CN": zhCN, "zh-TW": zhTW };

// The policy for a release's notes (CONTRIBUTING.md, Releases): user-facing features only, at most
// three items, each a bold title and one or two sentences, in every locale.
test("every release's notes are one to three items, each a title and a body of a sentence or two, in every locale", () => {
  for (const [release, items] of Object.entries(WHATS_NEW)) {
    assert.match(release, /^\d+\.\d+$/, `${release} is a release by its minor`);
    assert.ok(items.length >= 1 && items.length <= MAX_ITEMS, `${release} has 1 to ${MAX_ITEMS} items`);
    assert.equal(new Set(items).size, items.length, `${release}'s items are distinct`);
    for (const [locale, table] of Object.entries(TABLES)) {
      const notes = whatsNewNotes(release, key => table[key] ?? "");
      assert.ok(notes.title, `${locale} titles ${release}`);
      for (const item of notes.items) {
        assert.ok(item.title && item.body, `${locale} says ${release}.${item.id}`);
      }
    }
    for (const item of whatsNewNotes(release, key => en[key]).items) {
      assert.match(item.title, /\.$/, `${release}.${item.id}'s title is a phrase ending in a period`);
      const sentences = item.body.split(/(?<=[.!?])\s+/).filter(Boolean).length;
      assert.ok(sentences >= 1 && sentences <= 2, `${release}.${item.id}'s body is one or two sentences`);
    }
  }
});

test("an update shows the newest notes at or before its release, once; a new person, a release with none, and notes seen show nothing", () => {
  const notes = { "0.11": ["a"], "0.13": ["b"] };
  assert.equal(whatsNewEntry("0.11", [], notes), "0.11");  // updated to 0.11: its notes
  assert.equal(whatsNewEntry("0.11", ["0.11"], notes), null);  // dismissed, or a new person's first release
  assert.equal(whatsNewEntry("0.12", [], notes), "0.11");  // 0.10 to 0.12, which has none: 0.11's
  assert.equal(whatsNewEntry("0.12", ["0.12"], notes), null);  // a new person on 0.12 is shown nothing older
  assert.equal(whatsNewEntry("0.12", ["0.11"], notes), null);  // a release with no notes after the last seen
  assert.equal(whatsNewEntry("0.14", ["0.11"], notes), "0.13");  // skipped releases: the newest notes alone
  assert.equal(whatsNewEntry("0.10", [], notes), null);  // a release before any notes
  assert.equal(whatsNewEntry("1.0", ["0.13"], { ...notes, "1.0": ["c"] }), "1.0");
  assert.equal(whatsNewEntry(null, [], notes), null);  // a server that keeps none
  assert.equal(whatsNewEntry("0.11", null, notes), null);
});
