// The app's language: English or 简体中文, kept like the appearance is. The ids are the
// i18n core's (`@text-to-cad/ui/i18n`); this module is the host's side of it — what the
// browser says (`navigator.language`), where the person's choice is kept
// (`localStorage`, durable, unlike the tab's appearance) and the `<html lang>` attribute
// native controls and screen readers read. Environmental on purpose: the shared package
// stays free of the browser, and every host wires its own (`docs` on the boundaries).
import { DEFAULT_LOCALE, resolveLocale, setLocale } from "@text-to-cad/ui/i18n";

export const ENGLISH_LOCALE_ID = "en";
export const SIMPLIFIED_CHINESE_LOCALE_ID = "zh-CN";

/** Where the person's language is kept, beside the tab record's own key. */
export const LOCALE_STORAGE_KEY = "text-to-cad:locale:v1";

/** The languages the picker offers, in dictionary order. */
export const LOCALES = Object.freeze([ENGLISH_LOCALE_ID, SIMPLIFIED_CHINESE_LOCALE_ID]);

// The browser's storage and document, where this module runs; tests (plain node) pass their own.
const defaultStorage = () => (typeof window === "undefined" ? undefined : window.localStorage);
const defaultRoot = () => (typeof document === "undefined" ? undefined : document.documentElement);
const defaultLanguages = () => (typeof navigator === "undefined" ? [] : navigator.languages ?? [navigator.language]);

export function readStoredLocale(storage = defaultStorage()) {
  try {
    return String(storage.getItem(LOCALE_STORAGE_KEY) || "").trim();
  } catch {
    return "";
  }
}

export function writeStoredLocale(locale, storage = window.localStorage) {
  try {
    storage.setItem(LOCALE_STORAGE_KEY, locale);
  } catch { /* A page that cannot keep the choice still runs in it. */ }
}

/** The `<html lang>` attribute: one write, at startup and on the person's change. */
export function applyDocumentLocale(locale, root = defaultRoot()) {
  if (root) root.lang = locale;
}

/** What this browser runs in: the person's saved choice, else the browser's languages, else English. */
export function detectLocale({ stored = readStoredLocale(), languages = defaultLanguages() } = {}) {
  return resolveLocale([stored, ...languages]);
}

/** The one startup: read, run in it, name the document. Before the first paint (`main.tsx`). */
export function initLocale() {
  const locale = detectLocale();
  setLocale(locale);
  applyDocumentLocale(locale);
  return locale;
}

/** The person's change: run in it, keep it, name the document. */
export function changeLocale(locale, storage = defaultStorage()) {
  const next = LOCALES.includes(locale) ? locale : DEFAULT_LOCALE;
  setLocale(next);
  writeStoredLocale(next, storage);
  applyDocumentLocale(next);
  return next;
}
