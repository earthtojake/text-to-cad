/**
 * The viewer's i18n core: the locales it speaks and the lookup (which locale a person reads in is
 * `./locale.js`'s, which this re-exports). It is deliberately plain — no
 * React, no `navigator`, no storage, no `document`, and no locale of its own: which language a
 * view reads in is the host's to say (`environment.locale`, as it says `colorScheme`), and a
 * view hands the translator for it down (`../react.js`). So a pure module (`entry-menu.js`) and a
 * `node --test` run read it exactly as the browser does, taking the `t` they are given.
 */

import en from "./locales/en.js";
import ja from "./locales/ja.js";
import ko from "./locales/ko.js";
import zhCN from "./locales/zh-CN.js";
import zhTW from "./locales/zh-TW.js";
import { DEFAULT_LOCALE, LOCALES, localeForTag, resolveLocale } from "./locale.js";

export { DEFAULT_LOCALE, LOCALES, localeForTag, resolveLocale };

const TABLES = { "en": en, "zh-CN": zhCN, "zh-TW": zhTW, "ja": ja, "ko": ko };

/** A locale this viewer speaks: exact, else case-insensitive, else undefined. */
export function normalizeLocale(locale) {
  const wanted = String(locale || "").trim();
  return TABLES[wanted] ? wanted
    : LOCALES.find(supported => supported.toLowerCase() === wanted.toLowerCase());
}

/** A dictionary's answer, falling back to English, falling back to the key itself. */
function lookup(locale, key) {
  const table = TABLES[locale] || TABLES[DEFAULT_LOCALE];
  return table[key] ?? TABLES[DEFAULT_LOCALE][key] ?? key;
}

/** `t` under the locale this call names: `translateIn("zh-CN", "home.openAria", { name })`.
 * `{name}` braces take a value.
 * @param {string} locale
 * @param {string} key
 * @param {Record<string, unknown>} [params]
 */
export function translateIn(locale, key, params) {
  let text = lookup(normalizeLocale(locale) || DEFAULT_LOCALE, key);
  if (params) {
    for (const [name, value] of Object.entries(params)) {
      text = text.replaceAll(`{${name}}`, String(value));
    }
  }
  return text;
}

/**
 * The one lookup for a locale, `t(key, params)`: one function per locale, so a memo that
 * depends on `t` is redone when the language changes and on nothing else.
 * @param {string} [locale]
 * @returns {(key: string, params?: Record<string, unknown>) => string}
 */
export function translator(locale) {
  return TRANSLATORS[normalizeLocale(locale) || DEFAULT_LOCALE];
}

const TRANSLATORS = Object.fromEntries(LOCALES.map(locale => [locale, (key, params) => translateIn(locale, key, params)]));

/** English's `t`: what a pure helper reads when its caller hands it none. */
export const english = TRANSLATORS[DEFAULT_LOCALE];
