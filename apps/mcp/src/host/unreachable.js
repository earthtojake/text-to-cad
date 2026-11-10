/**
 * What a card says where its chat carries none of its calls to CAD's server and the engine cannot be
 * reached from it either (the Claude app's Code tab, where the host refuses a card's calls and keeps
 * it off this machine's loopback): one line, by whether the launch gave the CAD Viewer's page and
 * whether it was to show a model, and the button that opens that page. The app's notice says it
 * (`Notice.tsx`'s `Unreachable`), and so does the shell (`host/shell.ts`) where the app itself cannot
 * be loaded, its words taken from the same dictionaries when it is built (`scripts/shell-words.mjs`).
 */

/** The button that opens the CAD Viewer's page. */
export const OPEN_IN_VIEWER = 'cad.openInViewer';

/** Every key the notice says. */
export const UNREACHABLE_KEYS = Object.freeze(['cad.unreachable.openModel', 'cad.unreachable.openViewer',
  'cad.unreachable.askModel', 'cad.unreachable.askViewer', 'cad.unreachable.staleModel', 'cad.unreachable.staleViewer',
  OPEN_IN_VIEWER]);

/** A card that only says it cannot connect is as tall as its words, not a viewer's height: this, until they are measured. */
export const NOTICE_HEIGHT = 180;

/**
 * Why a card cannot reach CAD's server, where the server said (its refusal's `structuredContent.refused`,
 * `cad_server/mcp/server.py`'s `_app_only`): `capability`, the card's call carried none (or another
 * session's); `stale`, it carried one from before CAD restarted. Any other refusal says nothing here.
 * @param {{ isError?: boolean, structuredContent?: Record<string, unknown> } | undefined} result
 * @returns {'capability' | 'stale' | null}
 */
export function refusalOf(result) {
  const refused = result?.isError ? result.structuredContent?.refused : undefined;
  return refused === 'capability' || refused === 'stale' ? refused : null;
}

/**
 * The line's key: a view opened before CAD restarted is shown again; else the page offered where the
 * launch gave one, else the agent asked to open it.
 * @param {boolean} page
 * @param {boolean} model
 * @param {'capability' | 'stale' | null} [refused]
 */
export function unreachableKey(page, model, refused = null) {
  if (refused === 'stale') return model ? 'cad.unreachable.staleModel' : 'cad.unreachable.staleViewer';
  return page ? (model ? 'cad.unreachable.openModel' : 'cad.unreachable.openViewer')
    : (model ? 'cad.unreachable.askModel' : 'cad.unreachable.askViewer');
}

/**
 * How tall an inline card showing a notice is (`notice.css`'s `.cad-notice`): its words and its
 * padding, measured, so no empty frame stands around it at any width; `NOTICE_HEIGHT` where nothing
 * was laid out (a hidden frame).
 * @param {HTMLElement} notice
 * @returns {number}
 */
export function noticeHeight(notice) {
  const body = notice.firstElementChild;
  const style = getComputedStyle(notice);
  const height = (body ? body.getBoundingClientRect().height : 0)
    + (parseFloat(style.paddingTop) || 0) + (parseFloat(style.paddingBottom) || 0);
  return body && body.getBoundingClientRect().height > 0 ? Math.ceil(height) : NOTICE_HEIGHT;
}

/**
 * The launch's page of the CAD Viewer, where the engine gave one.
 * @param {{ browser?: unknown }} launch
 * @returns {string | null}
 */
export function viewerPage(launch) {
  try {
    return typeof launch.browser === 'string' ? new URL(launch.browser).href : null;
  } catch {
    return null;
  }
}
