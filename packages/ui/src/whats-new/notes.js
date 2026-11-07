/**
 * What's new: the notes of each release that brought something a person would want to know of, by
 * its minor version, and the rule for when a view shows them. Not every release has notes. An
 * entry is its items' ids, at most three; its words are the locale files' (`../i18n/locales`):
 * one title for every release (`whatsNew.title`, "What's New (v<release>.0)"), and per item `whatsNew.<release>.<item>.title` (bold, ending in a
 * period) and `.body` (one or two sentences; `code` in backticks). User-facing features only.
 * The notes ship in the page, so a view reads them from the server that served it, never the network.
 */

/** @type {Readonly<Record<string, readonly string[]>>} */
export const WHATS_NEW = Object.freeze({
  "0.11": Object.freeze(["boards", "updates"]),
});

/** At most this many items an entry. */
export const MAX_ITEMS = 3;

/** @param {string} release */
const order = release => release.split(".").map(Number);

/** Whether release `a` comes before `b` (both `<major>.<minor>`). @param {string} a @param {string} b */
export function before(a, b) {
  const [x, y] = [order(a), order(b)];
  return x[0] < y[0] || (x[0] === y[0] && x[1] < y[1]);
}

/**
 * The release whose notes a view shows, or null: the newest with notes at or before the release the
 * engine runs (`release`), when it is newer than every release the person has seen (`seen`, from the
 * settings: a new person's first release counts as seen, so they are shown nothing new). One dialog
 * an update: a person who skipped releases reads the newest notes alone.
 * @param {string | null | undefined} release
 * @param {readonly string[] | null | undefined} seen
 * @param {Readonly<Record<string, readonly string[]>>} [notes]
 * @returns {string | null}
 */
export function whatsNewEntry(release, seen, notes = WHATS_NEW) {
  if (!release || !Array.isArray(seen) || !/^\d+\.\d+$/.test(release)) return null;
  const newest = Object.keys(notes).filter(key => !before(release, key)).sort((a, b) => (before(a, b) ? 1 : -1))[0];
  if (!newest || seen.some(key => !before(key, newest))) return null;
  return newest;
}

/**
 * An entry's words under `t`: its title and items, each a bold title and a body.
 * @param {string} release
 * @param {(key: string) => string} t
 * @param {Readonly<Record<string, readonly string[]>>} [notes]
 */
export function whatsNewNotes(release, t, notes = WHATS_NEW) {
  return {
    title: t("whatsNew.title", { version: `${release}.0` }),
    items: (notes[release] ?? []).map(item => ({ id: item, title: t(`whatsNew.${release}.${item}.title`), body: t(`whatsNew.${release}.${item}.body`) })),
  };
}
