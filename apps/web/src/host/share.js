/**
 * The share service this page was served by, read at its API on the page's own origin and nowhere else
 * (`/v1/shares/<id>`): a share's stored bytes, for the view (`/<id>#key=<key>`), and its deletion, for the
 * delete page (`/<id>#delete=<secret>`). The key never leaves the page; the delete secret goes in one place,
 * the DELETE's `Authorization` header. Neither is in a URL, a log or storage. What the bytes are, and how
 * they open, is `@cad/core/client`'s `openShareArchive`.
 */
import { serverErrorMessage } from "@cad/core/client";

/** A share the service has none of (it never was, it expired, or it was deleted): its answer was 404. */
export const SHARE_GONE = "share-gone";

/** The API URL of share `id`, on `origin` (the page's own). */
export function shareApiUrl(id, origin = window.location.origin) {
  return new URL(`/v1/shares/${encodeURIComponent(id)}`, origin).href;
}

// Every request: nothing cached, no cookie, no referrer (the page's address is no one else's to read).
const QUIET = { cache: "no-store", credentials: "omit", referrerPolicy: "no-referrer" };

/** A refusal the service answered, in its own words where it said any (`{"error", "hint"}`). */
async function refusal(response, what) {
  let said = "";
  try { said = serverErrorMessage(await response.json()); } catch { said = ""; }
  return Object.assign(new Error(`The share service answered ${response.status} to ${what}${said ? `: ${said}` : "."}`), { status: response.status });
}

/**
 * The stored bytes of share `id` (`IV || ciphertext-and-tag`). SHARE_GONE for a 404; any other refusal is
 * an error with its `status`, and a network failure is the fetch's own.
 * @param {string} id
 * @param {{ fetch?: typeof globalThis.fetch, signal?: AbortSignal, origin?: string }} [options]
 * @returns {Promise<ArrayBuffer>}
 */
export async function fetchShare(id, { fetch: fetchImpl = globalThis.fetch, signal, origin } = {}) {
  const response = await fetchImpl(shareApiUrl(id, origin), { ...QUIET, signal });
  if (response.status === 404) throw Object.assign(new Error("This shared model has expired or was deleted."), { code: SHARE_GONE, status: 404 });
  if (!response.ok) throw await refusal(response, "the shared model's request");
  return response.arrayBuffer();
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
  const response = await fetchImpl(shareApiUrl(id, origin), { ...QUIET, method: "DELETE", headers: { Authorization: `Bearer ${secret}` } });
  if (response.ok) return "deleted";
  if (response.status === 404) return "gone";
  if (response.status === 403) return "refused";
  throw await refusal(response, "the deletion");
}
