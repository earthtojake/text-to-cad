import assert from "node:assert/strict";
import { test } from "node:test";

import { LOCALES, english, translator } from "../../../i18n/core.js";
import en from "../../../i18n/locales/en.js";
import { statusLabel, statusLine } from "./statusLabels.js";
import { loadingProgress } from "./loadingState.js";

test("every loading step the screen can show, and every update line, is said in the view's language", () => {
  const zh = translator("zh-CN");
  for (const phase of ["", "catalog", "compile", "generate", "meshing", "read", "geometry", "view"]) {
    const { label } = loadingProgress({ phase });
    assert.notEqual(statusLabel(label, zh), label, `${label} has a translation`);
  }
  assert.equal(statusLabel("Opening model", zh), "正在打开模型");
  assert.equal(statusLabel("Meshing parts 37/256…", zh), "正在网格化零件 37/256…");
  assert.equal(statusLabel("Updating model…", translator("ja")), "モデルを更新しています…");
  assert.equal(statusLabel("A file's own words", zh), "A file's own words", "anything else shows as it came");
  assert.equal(statusLabel("Opening model"), "Opening model", "English without a translator");
});

test("every stage of the engine's progress event is said in every language, by its key", () => {
  // The vocabulary is the engine's (`cad/engine/progress.py`: `STAGES`), keyed `progress.<kind>.<stage>`
  // in the locales; a policy test holds the two to each other. Here: each key reads as words in every
  // language, never as the key or as English, and an update line carries the count in flight.
  const keys = Object.keys(en).filter(key => key.startsWith("progress."));
  assert.ok(keys.length >= 13, keys);
  for (const locale of LOCALES) {
    const t = translator(locale);
    for (const key of keys) {
      const said = statusLabel(key, t);
      assert.notEqual(said, key, `${locale} says ${key}`);
      if (locale !== "en") assert.notEqual(said, en[key], `${locale} translates ${key}`);
    }
  }
  assert.equal(statusLabel("progress.build.body", translator("zh-CN")), "正在构建几何体");
  assert.equal(statusLine({ label: "progress.build.write", counts: "1/2" }), "Writing files 1/2…");
  assert.equal(statusLine({ label: "progress.build.write", counts: "1/2" }, translator("ja")), "ファイルを書き込んでいます 1/2…");
  assert.equal(statusLine({ label: "progress.export.read", counts: "" }, translator("ko")), "문서 읽는 중…");
  assert.equal(statusLine({ label: "Updating model…" }), "Updating model…", "a line of the page's own, as before");
  assert.equal(statusLabel("progress.build.nothing", english), "progress.build.nothing", "a key nobody has reads as itself");
});
