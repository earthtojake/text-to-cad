import type { ViewerAlert } from "../file-viewer/types.js";

// The project's notices (`GET /api/v1/server`'s `cadNotices`: `cad_server/notices.py`): words for every cad older than
// a release, each shown as the viewer's alert card until the person dismisses it, which the host keeps
// (`NoticeDismissals`: the viewer's, in this browser).

/** One notice, as the server says it: its id, its words (English, plain text) and its link, where it has one. */
export interface Notice {
  id: string;
  text: string;
  url?: string;
}

// A link the card follows: only the project's own site or repository, over https, as the feed and the server allow.
const NOTICE_URL = /^https:\/\/(?:texttocad\.dev|github\.com\/earthtojake\/text-to-cad)(?:[/?#][\x21-\x7e]*)?$/;

/** The notices of a server's answer that the page can show, each with an id and words; anything else is left out. */
export function noticesOf(given: unknown): Notice[] {
  if (!Array.isArray(given)) return [];
  return given.flatMap((notice: unknown) => {
    const { id, text, url } = (notice ?? {}) as Record<string, unknown>;
    if (typeof id !== "string" || !id || typeof text !== "string" || !text) return [];
    return [{ id, text, ...(typeof url === "string" && NOTICE_URL.test(url) ? { url } : {}) }];
  });
}

/**
 * Where the host keeps the notices the person dismissed (the viewer's: this browser's local storage): their ids read,
 * and one more kept. A store that throws is one that keeps nothing: the notice is shown again on the next page.
 */
export interface NoticeDismissals {
  dismissed(): readonly string[];
  dismiss(id: string): void;
}

/** The ids the host keeps as dismissed; none where it cannot say. */
export function dismissedOf(store: NoticeDismissals): Set<string> {
  try {
    const kept: unknown = store.dismissed();
    return new Set(Array.isArray(kept) ? kept.filter((id): id is string => typeof id === "string") : []);
  } catch {
    return new Set();
  }
}

/** A notice dismissed, kept by the host where it can; never failing. */
export function keepDismissed(store: NoticeDismissals, id: string): void {
  try {
    store.dismiss(id);
  } catch {
    // Shown again next time.
  }
}

/**
 * A notice as the viewer's alert card says it (`ViewerAlertCard`, through `CadViewer`'s `alert`): a warning that
 * blocks nothing, headed by the notice's own words, shown as text; "Learn more", its link, where it has one; and
 * Dismiss. No Report Issue: it is the project's own word.
 */
export function noticeAlert(notice: Notice, t: (key: string, params?: Record<string, unknown>) => string): ViewerAlert {
  return {
    severity: "warning", kind: "notice", blocking: false, reportable: false, title: notice.text,
    ...(notice.url ? { link: { label: t("alert.learnMore"), href: notice.url } } : {}),
    dismissLabel: t("alert.dismiss"),
  };
}
