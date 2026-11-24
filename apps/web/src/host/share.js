/**
 * The share service this page was served by, read at its API on the page's own origin and nowhere else
 * (`/v1/shares/<id>`): a share's sealed manifest and packs, for the view (`/<id>`: `shareService`, what
 * `@cad/core/client`'s `openShare` reads a share with), and its deletion, for the delete page
 * (`/<id>#delete=<secret>`). The delete secret goes in one place, the DELETE's `Authorization` header: never in
 * a URL, a log or storage. What the bytes are, and how they open, is `openShare`'s.
 */
import { serverErrorMessage } from "@cad/core/client";

/** A share the service has none of (it never was, it expired, or it was deleted): its answer was 404. */
export const SHARE_GONE = "share-gone";

/** The API URL of share `id`, on `origin` (the page's own). */
export function shareApiUrl(id, origin = window.location.origin) {
  return new URL(`/v1/shares/${encodeURIComponent(id)}`, origin).href;
}

// Every request: no cookie, no referrer (the page's address is no one else's to read).
const QUIET = { credentials: "omit", referrerPolicy: "no-referrer" };

/** A refusal the service answered, in its own words where it said any (`{"error", "hint"}`). */
async function refusal(response, what) {
  let said = "";
  try { said = serverErrorMessage(await response.json()); } catch { said = ""; }
  return Object.assign(new Error(`The share service answered ${response.status} to ${what}${said ? `: ${said}` : "."}`), { status: response.status });
}

/**
 * The service's reads of share `id` (`ShareService`): its sealed manifest (`GET /v1/shares/<id>`, never from a
 * cache, as a share shared again changes in place), SHARE_GONE for a 404; and one sealed pack
 * (`GET /v1/shares/<id>/packs/<pack id>`, as the browser's cache keeps it: a pack is named by its content and
 * never changes). Any other refusal is an error with its `status`, and a network failure is the fetch's own.
 * @param {string} id
 * @param {{ fetch?: typeof globalThis.fetch, origin?: string }} [options]
 * @returns {import("@cad/core/client").ShareService}
 */
export function shareService(id, { fetch: fetchImpl = globalThis.fetch, origin } = {}) {
  const url = shareApiUrl(id, origin);
  return {
    async manifest({ signal } = {}) {
      const response = await fetchImpl(url, { ...QUIET, cache: "no-store", signal });
      if (response.status === 404) throw Object.assign(new Error("This shared model has expired or was deleted."), { code: SHARE_GONE, status: 404 });
      if (!response.ok) throw await refusal(response, "the shared model's request");
      return response.arrayBuffer();
    },
    async pack(pack, { signal } = {}) {
      const response = await fetchImpl(`${url}/packs/${encodeURIComponent(pack)}`, { ...QUIET, signal });
      if (!response.ok) throw await refusal(response, "the request for a pack of the shared model");
      return response.arrayBuffer();
    },
  };
}

/**
 * Delete share `id` with its delete secret, sent as the request's `Authorization` alone: `"deleted"` (204),
 * `"gone"` where there was none to delete (404: expired, or deleted before), `"refused"` where the secret is
 * not the share's (403). Any other answer is an error with its `status`.
 * @param {string} id
 * @param {string} secret
 * @param {{ fetch?: typeof globalThis.fetch, origin?: string }} [options]
 * @returns {Promise<"deleted" | "gone" | "refused">}
 */
export async function deleteShare(id, secret, { fetch: fetchImpl = globalThis.fetch, origin } = {}) {
  const response = await fetchImpl(shareApiUrl(id, origin), { ...QUIET, cache: "no-store", method: "DELETE",
    headers: { Authorization: `Bearer ${secret}` } });
  if (response.ok) return "deleted";
  if (response.status === 404) return "gone";
  if (response.status === 403) return "refused";
  throw await refusal(response, "the deletion");
}
