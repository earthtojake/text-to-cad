/**
 * The viewer's i18n core: the locales it speaks and the lookup. It is deliberately plain — no
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

/** The locales the viewer ships, in a picker's list order. */
export const LOCALES = Object.freeze(["en", "zh-CN", "zh-TW", "ja", "ko"]);
export const DEFAULT_LOCALE = "en";

const TABLES = { "en": en, "zh-CN": zhCN, "zh-TW": zhTW, "ja": ja, "ko": ko };

/** A locale this viewer speaks: exact, else case-insensitive, else undefined. */
export function normalizeLocale(locale) {
  const wanted = String(locale || "").trim();
  return TABLES[wanted] ? wanted
    : LOCALES.find(supported => supported.toLowerCase() === wanted.toLowerCase());
}

/**
 * The locale a language tag (BCP 47, or a platform's `zh_TW`) reads in, or undefined. Chinese goes
 * by script, else region: Traditional (`zh-Hant`, Taiwan, Hong Kong, Macau) is `zh-TW`, and
 * Simplified (`zh-Hans`, mainland China, Singapore, or plain `zh`) is `zh-CN`; any `ja` is `ja`,
 * any `ko` is `ko`, any `en` is `en`.
 * @param {unknown} tag
 */
export function localeForTag(tag) {
  const subtags = String(tag || "").trim().replaceAll("_", "-").toLowerCase().split("-").filter(Boolean);
  const [language, ...rest] = subtags;
  if (language === "zh") return rest.includes("hant") || (!rest.includes("hans") && rest.some(part => ["tw", "hk", "mo"].includes(part))) ? "zh-TW" : "zh-CN";
  return ["en", "ja", "ko"].includes(language) ? language : undefined;
}

/**
 * The locale to run in, from the context's language tags, best first (the browser's languages,
 * the host's locale before them): the first one this viewer speaks wins (`localeForTag`), and
 * nothing understood is English.
 */
export function resolveLocale(preferences) {
  for (const preference of preferences || []) {
    const locale = localeForTag(preference);
    if (locale) return locale;
  }
  return DEFAULT_LOCALE;
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
