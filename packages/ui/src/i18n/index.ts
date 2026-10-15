/**
 * The viewer's i18n: `useI18n()` for a component, `t` for a pure helper, and
 * the locale state between them (`./core.js` — deliberately environment-free;
 * the host detects, keeps and applies the choice). The dictionaries live in
 * `./locales/`, `en` first: it is every key set's source of truth.
 */
export {
  DEFAULT_LOCALE,
  LOCALES,
  getLocale,
  normalizeLocale,
  resolveLocale,
  setLocale,
  subscribe,
  translate,
  translateIn,
} from "./core.js";
export { useI18n } from "./react.js";
