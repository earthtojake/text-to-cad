import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { normalizeLocale, resolveLocale } from "./core.js";

/** What a CAD app's server keeps of the person's language: their choice, or none (Automatic). */
export interface LanguageChoice { locale: string | null }

/**
 * The app menu's Language row: the language in force, the one the context infers (what
 * Automatic means), the person's choice (null for Automatic) and how they change it.
 */
export interface LanguageSetting {
  locale: string;
  inferred: string;
  choice: string | null;
  onChoiceChange: (choice: string | null) => void;
}

/**
 * The person's language. By default it is inferred from the context the view runs in —
 * `preferred`, best first: the browser's languages, or the host's locale before them — as the
 * first one this viewer speaks, else English. A language chosen in the app menu overrides that,
 * and Automatic clears the override; the choice is kept by the host's server (`language()`
 * reads, `language(locale | null)` answers: `settings.json` in cadgen's state directory, one
 * choice for every CAD view of the person's). It is read once, read again whenever the person
 * comes back to the page (another view may have changed it meanwhile), and only the latest
 * read's reply is kept, so a read sent just before a change can never undo it; an answer that did
 * not arrive is read back. `initial` is a choice the host already read, so the first paint is in
 * it.
 */
export function useLanguage(language: (locale?: string | null) => Promise<LanguageChoice>,
  { preferred = [], initial = null }: { preferred?: readonly (string | undefined)[]; initial?: string | null } = {}) {
  const [choice, setChoice] = useState<string | null>(() => normalizeLocale(initial) ?? null);
  const turn = useRef(0);
  const read = useCallback(function read(change?: string | null) {
    const mine = ++turn.current;
    void language(change).then(
      next => { if (mine === turn.current) setChoice(normalizeLocale(next?.locale) ?? null); },
      () => { if (change !== undefined && mine === turn.current) read(); });
  }, [language]);
  useEffect(() => { read(); }, [read]);
  useEffect(() => {
    const recheck = () => read();
    window.addEventListener("focus", recheck);
    return () => window.removeEventListener("focus", recheck);
  }, [read]);
  const key = preferred.join("\n");
  const inferred = useMemo(() => resolveLocale(key.split("\n")), [key]);
  const locale = choice ?? inferred;
  const change = useCallback((next: string | null) => {
    const wanted = next === null ? null : normalizeLocale(next);
    if (wanted === undefined) return;
    setChoice(wanted);
    read(wanted);
  }, [read]);
  const setting = useMemo<LanguageSetting>(() => ({ locale, inferred, choice, onChoiceChange: change }), [locale, inferred, choice, change]);
  return { locale, language: setting };
}
