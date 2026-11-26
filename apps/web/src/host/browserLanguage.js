/**
 * The person's language where the page has no server to keep it (a view bundle's page): their choice in the
 * app menu, kept in this browser's localStorage, so it holds for every page of this viewer the browser opens,
 * as `settings.json` does for every CAD view where there is an engine. The same call as the CAD client's
 * `language` (`@cad/ui/i18n`'s `useLanguage` reads and answers through it): no argument reads the choice,
 * `null` clears it (Automatic), a locale keeps it.
 */
export const LANGUAGE_KEY = "text-to-cad:language";

/**
 * @param {Pick<Storage, "getItem" | "setItem" | "removeItem">} [storage]
 * @returns {(locale?: string | null) => Promise<{ locale: string | null }>}
 */
export function browserLanguage(storage = window.localStorage) {
  return async (locale) => {
    if (locale === null) storage.removeItem(LANGUAGE_KEY);
    else if (typeof locale === "string") storage.setItem(LANGUAGE_KEY, locale);
    return { locale: storage.getItem(LANGUAGE_KEY) || null };
  };
}
