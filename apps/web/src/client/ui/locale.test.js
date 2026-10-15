import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import vm from "node:vm";

import {
  applyDocumentLocale,
  changeLocale,
  detectLocale,
  ENGLISH_LOCALE_ID,
  LOCALES,
  LOCALE_STORAGE_KEY,
  readStoredLocale,
  SIMPLIFIED_CHINESE_LOCALE_ID,
  writeStoredLocale
} from "./locale.js";
import { getLocale, setLocale } from "@text-to-cad/ui/i18n";

test.afterEach(() => setLocale(ENGLISH_LOCALE_ID));

function createStorage(entries = {}) {
  return {
    getItem: (key) => key in entries ? entries[key] : null,
    setItem: (key, value) => { entries[key] = String(value); },
  };
}

test("English and 简体中文 are the languages, and the browser's own tags land on one", () => {
  assert.deepEqual(LOCALES, ["en", "zh-CN"]);
  assert.equal(detectLocale({ stored: SIMPLIFIED_CHINESE_LOCALE_ID, languages: ["en"] }), SIMPLIFIED_CHINESE_LOCALE_ID, "the person's choice first");
  assert.equal(detectLocale({ stored: ENGLISH_LOCALE_ID, languages: ["zh-CN"] }), ENGLISH_LOCALE_ID, "a kept English beats the browser's Chinese");
  assert.equal(detectLocale({ stored: "", languages: ["fr-FR", "zh-TW"] }), SIMPLIFIED_CHINESE_LOCALE_ID, "a zh-TW browser reads zh-CN");
  assert.equal(detectLocale({ stored: "nonsense", languages: ["fr-FR", "en-US"] }), ENGLISH_LOCALE_ID);
  assert.equal(detectLocale({ stored: "", languages: [] }), ENGLISH_LOCALE_ID);
  assert.equal(detectLocale({ languages: ["zh_CN"] }), SIMPLIFIED_CHINESE_LOCALE_ID, "a Windows underscore tag");
});

test("a saved locale is read and written beside the tab record's key, and a blocked store reads as none", () => {
  const storage = createStorage({ [LOCALE_STORAGE_KEY]: SIMPLIFIED_CHINESE_LOCALE_ID });
  assert.equal(readStoredLocale(storage), SIMPLIFIED_CHINESE_LOCALE_ID);
  writeStoredLocale(ENGLISH_LOCALE_ID, storage);
  assert.equal(storage.getItem(LOCALE_STORAGE_KEY), ENGLISH_LOCALE_ID);
  const blocked = { getItem() { throw new Error("blocked"); }, setItem() { throw new Error("blocked"); } };
  assert.equal(readStoredLocale(blocked), "");
  assert.doesNotThrow(() => writeStoredLocale(ENGLISH_LOCALE_ID, blocked));
});

test("applying a locale names the document; changing one runs the app in it, keeps it and names it", () => {
  const root = { lang: ENGLISH_LOCALE_ID };
  applyDocumentLocale(SIMPLIFIED_CHINESE_LOCALE_ID, root);
  assert.equal(root.lang, SIMPLIFIED_CHINESE_LOCALE_ID);
  assert.doesNotThrow(() => applyDocumentLocale(SIMPLIFIED_CHINESE_LOCALE_ID, null));
  const storage = createStorage();
  const changed = changeLocale(SIMPLIFIED_CHINESE_LOCALE_ID, storage);
  assert.equal(changed, SIMPLIFIED_CHINESE_LOCALE_ID);
  assert.equal(getLocale(), SIMPLIFIED_CHINESE_LOCALE_ID);
  assert.equal(storage.getItem(LOCALE_STORAGE_KEY), SIMPLIFIED_CHINESE_LOCALE_ID);
  assert.equal(changeLocale("fr", storage), ENGLISH_LOCALE_ID, "a language the viewer does not speak is English");
  assert.equal(getLocale(), ENGLISH_LOCALE_ID);
  assert.equal(storage.getItem(LOCALE_STORAGE_KEY), ENGLISH_LOCALE_ID);
});

/*
  The page's first paint, before any module loads, reads the language the way `locale.js` reads
  it: the saved choice, else the browser's, and names `<html>` so the first painted strings and
  the attribute already agree (`index.html`, its second head script).
*/
function firstPaint({ stored, languages = [], blocked = false }) {
  const html = readFileSync(new URL("../../../index.html", import.meta.url), "utf8");
  const scripts = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map((match) => match[1]);
  const root = { lang: "en" };
  vm.runInNewContext(scripts[1], {
    document: { documentElement: root },
    window: { navigator: { languages }, get localStorage() {
      if (blocked) throw new Error("blocked");
      return { getItem: (key) => (key === "text-to-cad:locale:v1" && stored !== undefined ? stored : null) };
    } }
  });
  return root;
}

test("the first paint names the document in the saved language, else the browser's, else English", () => {
  const html = readFileSync(new URL("../../../index.html", import.meta.url), "utf8");
  assert.ok(html.indexOf('lang="en"') < html.indexOf("</head>"), "the page ships as English and fixes itself before paint");
  assert.equal(firstPaint({ stored: "zh-CN" }).lang, "zh-CN");
  assert.equal(firstPaint({ stored: "zh-CN", languages: ["en"] }).lang, "zh-CN", "a kept choice beats the browser");
  assert.equal(firstPaint({ stored: "en", languages: ["zh-CN"] }).lang, "en", "a kept English is kept, never a sentinel for 'ask the browser'");
  assert.equal(firstPaint({ stored: "", languages: ["zh-TW"] }).lang, "zh-CN");
  assert.equal(firstPaint({ stored: "nonsense", languages: ["fr-FR"] }).lang, "en");
  assert.equal(firstPaint({ blocked: true, languages: [] }).lang, "en", "blocked storage still paints");
});
