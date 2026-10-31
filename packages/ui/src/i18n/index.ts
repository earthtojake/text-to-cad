/**
 * The viewer's i18n: `useI18n()` for a component, `translator(locale)` for a pure helper, and
 * `I18nProvider`, which `FileViewer` and `CadViewer` put around what they draw in the language
 * the host names (`environment.locale`). The core (`./core.js`) holds no locale of its own; a
 * host infers the person's language, keeps their choice (`useLanguage`) and hands it down. The
 * dictionaries live in `./locales/`, `en` first: it is every key set's source of truth.
 */
export {
  DEFAULT_LOCALE,
  LOCALES,
  english,
  normalizeLocale,
  resolveLocale,
  translateIn,
  translator,
} from "./core.js";
export { I18nProvider, useI18n } from "./react.js";
export { useLanguage, type LanguageChoice, type LanguageSetting } from "./useLanguage.js";
