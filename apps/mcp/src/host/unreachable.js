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
  'cad.unreachable.askModel', 'cad.unreachable.askViewer', OPEN_IN_VIEWER]);

/** A card that only says it cannot connect is as tall as its words, not a viewer's height. */
export const NOTICE_HEIGHT = 180;

/**
 * The line's key: the page offered where the launch gave one, else the agent asked to open it.
 * @param {boolean} page
 * @param {boolean} model
 */
export function unreachableKey(page, model) {
  return page ? (model ? 'cad.unreachable.openModel' : 'cad.unreachable.openViewer')
    : (model ? 'cad.unreachable.askModel' : 'cad.unreachable.askViewer');
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
