/**
 * Whether the page shows a view bundle, and which: its address's `bundle` query parameter, the URL of the
 * bundle's folder (`cad <type> export SRC DST.view`) resolved against the page's own, on the page's own
 * origin (`?bundle=arm.view/`, `?bundle=/bundles/arm.view/`). A page with no `bundle` is the engine's page,
 * which reads its server as it always has: the parameter is the whole of the choice, made once, at start-up.
 */
export const BUNDLE_PARAM = "bundle";

/**
 * The URL of the bundle the address names, or null where it names none. A bundle on another origin is
 * refused, as the page reads its own origin alone.
 * @param {string} [href]  The page's address.
 * @returns {string | null}
 */
export function readBundleAddress(href = window.location.href) {
  const page = new URL(href);
  const named = page.searchParams.get(BUNDLE_PARAM);
  if (named === null) return null;
  if (!named.trim()) throw new Error("The page's address names no view bundle: ?bundle= wants the URL of its folder.");
  const bundle = new URL(named.trim(), page);
  if (bundle.origin !== page.origin) throw new Error(`This page opens a view bundle of its own origin (${page.origin}) alone, not ${bundle.origin}.`);
  bundle.search = "";
  bundle.hash = "";
  if (!bundle.pathname.endsWith("/")) bundle.pathname += "/";
  return bundle.href;
}
