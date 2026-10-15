import { useSyncExternalStore } from "react";

import { getLocale, setLocale, subscribe, translate } from "./core.js";

/**
 * The component's view of the locale: `{ locale, t, setLocale }`, where `t`
 * reads the current one. The subscription is the point — a locale change puts
 * every mounted reader back on the screen in the new language, and a re-render
 * is also what carries a pure helper's `t()` (`entry-menu.js`) along.
 */
export function useI18n() {
  const locale = useSyncExternalStore(subscribe, getLocale, getLocale);
  return { locale, setLocale, t: translate };
}
