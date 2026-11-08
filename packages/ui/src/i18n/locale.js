/**
 * Which of the viewer's locales a person reads in: the locales and the rule that picks one from the
 * language tags a context gives, and no dictionary. `./core.js` holds the dictionaries and re-exports
 * these; a page that says a few words before anything else loads (the CAD app's shell) reads its
 * words' locale here, without carrying every locale's dictionary.
 */

/** The locales the viewer ships, in a picker's list order. */
export const LOCALES = Object.freeze(["en", "zh-CN", "zh-TW", "ja", "ko"]);
export const DEFAULT_LOCALE = "en";

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
