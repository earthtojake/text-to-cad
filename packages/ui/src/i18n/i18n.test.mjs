import assert from "node:assert/strict";
import { test } from "node:test";

import en from "./locales/en.js";
import zhCN from "./locales/zh-CN.js";
import { DEFAULT_LOCALE, LOCALES, getLocale, normalizeLocale, resolveLocale, setLocale, subscribe, translate, translateIn } from "./core.js";

test("every locale answers with the same keys as English, and both agree on placeholders", () => {
  for (const locale of LOCALES) {
    const table = locale === "zh-CN" ? zhCN : en;
    assert.deepEqual(Object.keys(table).sort(), Object.keys(en).sort(), `${locale}'s keys drift from en's`);
    for (const [key, text] of Object.entries(table)) {
      const wanted = [...String(en[key]).matchAll(/\{(\w+)\}/g)].map(match => match[1]).sort().join(",");
      const got = [...String(text).matchAll(/\{(\w+)\}/g)].map(match => match[1]).sort().join(",");
      assert.equal(got, wanted, `${locale}.${key}'s placeholders drift from en's`);
    }
  }
  assert.equal(LOCALES[0], DEFAULT_LOCALE, "English is first and the default");
});

test("a locale's own name is written in that language, in every dictionary", () => {
  assert.equal(en["language.en"], "English");
  assert.equal(zhCN["language.en"], "English");
  assert.equal(en["language.zh-CN"], "简体中文");
  assert.equal(zhCN["language.zh-CN"], "简体中文");
});

test("normalizeLocale takes the exact locale, else the case-folded one, else nothing", () => {
  assert.equal(normalizeLocale("en"), "en");
  assert.equal(normalizeLocale("zh-CN"), "zh-CN");
  assert.equal(normalizeLocale("ZH-cn"), "zh-CN");
  assert.equal(normalizeLocale("fr"), undefined);
  assert.equal(normalizeLocale(""), undefined);
  assert.equal(normalizeLocale(undefined), undefined);
});

test("resolveLocale takes the first preference the viewer speaks, by exact tag or language", () => {
  assert.equal(resolveLocale(["zh-CN", "en"]), "zh-CN");
  assert.equal(resolveLocale(["fr-FR", "zh-TW", "en"]), "zh-CN", "a zh-TW browser reads zh-CN");
  assert.equal(resolveLocale(["fr-FR", "en-US"]), "en");
  assert.equal(resolveLocale(["zh_TW", "en"]), "zh-CN", "a Windows zh_TW tag lands on zh-CN");
  assert.equal(resolveLocale(["fr-FR", "de-DE"]), "en", "nothing understood is English");
  assert.equal(resolveLocale([]), "en");
  assert.equal(resolveLocale(undefined), "en");
});

test("translate reads the current locale, fills braces, and falls back to English then the key", () => {
  setLocale("zh-CN");
  try {
    assert.equal(translate("file.missing"), "文件不存在");
    assert.equal(translate("home.openAria", { name: "bracket.step" }), "打开 bracket.step");
  } finally {
    setLocale(DEFAULT_LOCALE);
  }
  assert.equal(translate("file.missing"), "File does not exist");
  assert.equal(translate("display.partColorN", { n: 2 }), "Part color 2");
});

test("a locale that misses a key reads English; a key nobody has reads as itself", () => {
  assert.equal(translateIn("zh-CN", "home.byline"), "构建万物。");
  assert.equal(translateIn("en", "home.byline"), "Build anything.");
  assert.equal(translateIn("zh-CN", "no.such.key"), "no.such.key");
  assert.equal(translateIn("fr", "file.missing"), "File does not exist", "an unsupported locale reads English");
});

test("setLocale tells its subscribers once per change, and subscribe can stop listening", () => {
  const heard = [];
  const stop = subscribe(() => heard.push(getLocale()));
  setLocale("zh-CN");
  setLocale("zh-CN");
  stop();
  setLocale(DEFAULT_LOCALE);
  assert.deepEqual(heard, ["zh-CN"], "no second call for the same locale, none after unsubscribing");
  assert.equal(getLocale(), DEFAULT_LOCALE);
});
