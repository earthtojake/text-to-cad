import { createContext, createElement, useContext, useMemo } from "react";

import { DEFAULT_LOCALE, normalizeLocale, translator } from "./core.js";

const I18nContext = createContext({ locale: DEFAULT_LOCALE, t: translator(DEFAULT_LOCALE) });

/**
 * The language a view reads in, from its host (`environment.locale`): `FileViewer` and
 * `CadViewer` put it around everything they draw, the nodes a host hands them (the update
 * button, the home's links) included. A locale this viewer does not speak reads English.
 *
 * @param {{ locale?: string, children?: import("react").ReactNode }} props
 */
export function I18nProvider({ locale, children }) {
  const resolved = normalizeLocale(locale) || DEFAULT_LOCALE;
  const value = useMemo(() => ({ locale: resolved, t: translator(resolved) }), [resolved]);
  return createElement(I18nContext.Provider, { value }, children);
}

/**
 * The component's view of the language: `{ locale, t }`. `t` is one function per locale, so a
 * memo that lists it is redone when the person changes language, and a pure helper handed it
 * (`entryMenu(platform, capabilities, t)`) answers in that language.
 */
export function useI18n() {
  return useContext(I18nContext);
}
