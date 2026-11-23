/**
 * Open in new tab (`ViewerHost.navigation.openBeside`, `kind: "tab"`): a target's own address (`hrefOf`), in a new
 * tab of this browser. The address is this origin's, so the page's session cookie admits the tab, as it does a
 * download (`downloads.ts`); it carries the page's link too, where the address has one. The tab is opened as the
 * browser opens any: nothing here takes the keyboard to it or back.
 *
 * A document named by its path has no address until the server has said its id (`resolve`: its path to its
 * document's id). A browser lets a page open a tab only inside the press that asked, so that tab is opened at once,
 * empty, and sent to the page when its id is known; if the file cannot be resolved the tab is closed, and the failure
 * is the caller's to say.
 *
 * @param {{ hrefOf(target: object): string | null, resolve(path: string): Promise<string>,
 *   page?: Pick<Window, "open"> & { location: Pick<Location, "href"> } }} options
 * @returns {(target: { document: string } | { home: object }) => Promise<void>}
 */
export function createNewTabOpener({ hrefOf, resolve, page = window }) {
  const absolute = address => new URL(address, page.location.href).href;
  return async target => {
    const address = hrefOf(target);
    if (address) { page.open(absolute(address), "_blank", "noopener"); return; }
    if (!("document" in target)) return;
    const tab = page.open("", "_blank");
    try {
      const id = await resolve(target.document);
      const found = id ? hrefOf({ document: id }) : null;
      if (!found) throw new Error(`File does not exist: ${target.document}`);
      // A tab this page opened without `noopener` (so it could be sent on) is cut off from it before it loads.
      if (tab) { tab.opener = null; tab.location.replace(absolute(found)); }
      else page.open(absolute(found), "_blank", "noopener");
    } catch (error) {
      tab?.close();
      throw error;
    }
  };
}
