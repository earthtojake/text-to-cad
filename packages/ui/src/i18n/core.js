/**
 * The viewer's i18n core: the locale every string is read in, and `t`, the one
 * lookup. It is deliberately plain — no React, no `navigator`, no storage, no
 * `document` — so a pure module (`entry-menu.js`, `loadingMessage.js`) and a
 * `node --test` run can read it exactly as the browser does, and so the
 * dependency checks stay clean: the environment's part (detecting the locale,
 * keeping the choice, naming the `<html>` element) belongs to the host, which
 * calls `setLocale` at startup and on the person's change (`apps/web`'s
 * `client/ui/locale.js`).
 *
 * A component that shows strings subscribes with `useI18n()` (`../react.js`,
 * `useSyncExternalStore` over `subscribe`), so a change of locale re-renders
 * it; a pure helper called during that render reads `t`'s current answer.
 */

import en from "./locales/en.js";
import zhCN from "./locales/zh-CN.js";

/** The locales the viewer ships, in a picker's list order. */
export const LOCALES = Object.freeze(["en", "zh-CN"]);
export const DEFAULT_LOCALE = "en";

const TABLES = { "en": en, "zh-CN": zhCN };

/** A locale this viewer speaks: exact, else case-insensitive, else undefined. */
export function normalizeLocale(locale) {
  const wanted = String(locale || "").trim();
  return TABLES[wanted] ? wanted
    : LOCALES.find(supported => supported.toLowerCase() === wanted.toLowerCase());
}

/**
 * The locale to run in, from the host's preferences in order (a saved choice,
 * then what the person's browser names, best first): the first one this viewer
 * speaks wins; a `zh_TW` browser lands on `zh-CN` through its `zh` primary
 * subtag; nothing understood is English.
 */
export function resolveLocale(preferences) {
  for (const preference of preferences || []) {
    const locale = normalizeLocale(preference);
    if (locale) return locale;
    const primary = String(preference || "").trim().toLowerCase().split("-")[0].split("_")[0];
    const byLanguage = primary && LOCALES.find(supported => supported.toLowerCase().split("-")[0] === primary);
    if (byLanguage) return byLanguage;
  }
  return DEFAULT_LOCALE;
}

let current = DEFAULT_LOCALE;
const listeners = new Set();

/** The locale strings are read in now. */
export function getLocale() {
  return current;
}

/** Run in another locale, telling the subscribers (`useI18n`). */
export function setLocale(locale) {
  const next = normalizeLocale(locale) || DEFAULT_LOCALE;
  if (next === current) return;
  current = next;
  for (const listener of listeners) listener();
}

/** `useSyncExternalStore`'s subscription: the one way a locale change is heard. */
export function subscribe(listener) {
  listeners.add(listener);
  return () => { listeners.delete(listener); };
}

/** A dictionary's answer, falling back to English, falling back to the key itself. */
function lookup(locale, key) {
  const table = TABLES[locale] || TABLES[DEFAULT_LOCALE];
  return table[key] ?? TABLES[DEFAULT_LOCALE][key] ?? key;
}

/** The one lookup: `t("home.openAria", { name })`. `{name}` braces take a value.
 * @param {string} key
 * @param {Record<string, unknown>} [params]
 */
export function translate(key, params) {
  let text = lookup(current, key);
  if (params) {
    for (const [name, value] of Object.entries(params)) {
      text = text.replaceAll(`{${name}}`, String(value));
    }
  }
  return text;
}

/** `t` under the locale this call names, whatever is current.
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
