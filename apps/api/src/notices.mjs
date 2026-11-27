/**
 * The notices, at their own address, the same for everyone:
 *
 *   GET /v1/notices   {"notices": [{"id": "install-moved", "below": "0.13.0", "text": "...", "url": "https://..."}]}
 *
 * the words the project shows to every cad older than a release, for the computers a release cannot bring along
 * (README, "Posting a notice"). A cad from the first release that reads them on reads them at most once an hour in the
 * background, beside PyPI, which says which release is newest (`cad_server/updates.py` in packages/cad), and checks each
 * by the same rules again (`parse_notices`): what it is answered is never trusted. With none posted, `{"notices": []}`.
 * Read from the Vercel project's settings alone, never from PyPI, so it answers whatever PyPI does.
 */

const RELEASE = /^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$/; // `cad_server/updates.py`'s own `_RELEASE`
const NOTICE_ID = /^[a-z0-9-]{1,40}$/;
const NOTICE_TEXT_MAX = 240; // characters (code points), as Python counts them
const NOTICE_CONTROL = /[\u0000-\u001f\u007f-\u009f\u2028\u2029]/u; // control characters and every line break
const NOTICE_URL = /^https:\/\/(?:texttocad\.dev|github\.com\/earthtojake\/text-to-cad)(?:[/?#][\x21-\x7e]*)?$/;
const NOTICE_URL_MAX = 500;
export const NOTICES_MAX = 10;

/**
 * Why a notice is refused, or null for one kept: `{id, below, text, url?}`, `id` a short slug (what a cad keeps a
 * dismissal and its once a day by), `below` the release every cad older than which it is for, `text` one line of plain
 * text, and `url`, where there is one, on texttocad.dev or the project's GitHub repository, over https.
 */
function noticeRefused(notice) {
  if (!notice || typeof notice !== 'object' || Array.isArray(notice)) return 'not an object';
  const { id, below, text, url } = notice;
  if (typeof id !== 'string' || !NOTICE_ID.test(id)) return 'id';
  if (typeof below !== 'string' || !RELEASE.test(below)) return 'below';
  if (typeof text !== 'string' || /^ *$/.test(text) || [...text].length > NOTICE_TEXT_MAX || NOTICE_CONTROL.test(text)) return 'text';
  if (url !== undefined && (typeof url !== 'string' || url.length > NOTICE_URL_MAX || !NOTICE_URL.test(url))) return 'url';
  return null;
}

/**
 * The notices the Vercel project posts: `CAD_NOTICES`, a JSON list of `{id, below, text, url?}` (README, "Posting a
 * notice"), each kept with those keys alone, in order, at most `NOTICES_MAX`, an id once. An entry that breaks a rule
 * is dropped, and logged with the rule so a mistake is seen; a variable that is no JSON list gives none, logged.
 * Unset or blank: none, and nothing logged.
 */
export function noticesOf(env = {}, log = console.error) {
  const given = String(env?.CAD_NOTICES ?? '').trim();
  if (!given) return [];
  let list;
  try {
    list = JSON.parse(given);
  } catch {
    log('notices: CAD_NOTICES is not JSON');
    return [];
  }
  if (!Array.isArray(list)) {
    log('notices: CAD_NOTICES is not a list');
    return [];
  }
  const notices = [];
  list.forEach((notice, at) => {
    const refused = noticeRefused(notice) ?? (notices.some(kept => kept.id === notice.id) ? 'id named twice'
      : notices.length >= NOTICES_MAX ? `more than ${NOTICES_MAX}` : null);
    if (refused) {
      log(`notices: CAD_NOTICES entry ${at} dropped:`, refused);
      return;
    }
    const { id, below, text, url } = notice;
    notices.push(Object.freeze({ id, below, text, ...(url === undefined ? {} : { url }) }));
  });
  if (notices.length) log('notices:', notices.map(({ id, below }) => `${id} (below ${below})`).join(', '));
  return Object.freeze(notices);
}
