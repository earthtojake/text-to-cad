import { useEffect } from "react";
import { isDocumentId } from "@cad/core/lib/cadRefs.js";

// The least time from one ask for the next version to the next: the viewer holds an ask about this
// long, and a host whose calls share a few slots (the CAD app's) answers one at once.
const VERSION_PACE_MS = 1000;

const pause = (ms, signal) => new Promise((resolve, reject) => {
  const timer = setTimeout(resolve, ms);
  signal.addEventListener("abort", () => { clearTimeout(timer); reject(signal.reason); }, { once: true });
});

/**
 * A document the engine holds by its id alone (an implicit's), kept current with the engine: the
 * page waits on it for its next version (`client.documentVersion`), about once a second, and each new
 * one reads the document's catalog row again (`client.refresh`), whose new `url` and `hash` the
 * renderer loads as it loads a file written again. A file is followed by the catalog's own reads, and
 * a client that cannot ask a version waits on nothing.
 *
 * @param {{ client: { documentVersion?: Function, refresh?: Function }, file: string }} options
 */
export function useDocumentVersion({ client, file }) {
  useEffect(() => {
    if (!isDocumentId(file) || typeof client?.documentVersion !== "function" || typeof client.refresh !== "function") return undefined;
    const controller = new AbortController();
    const { signal } = controller;
    (async () => {
      let version = "";
      while (!signal.aborted) {
        const asked = performance.now();
        try {
          const answer = await client.documentVersion(file, version, { signal });
          if (answer?.version && answer.version !== version) {
            await client.refresh({ file, signal });
            version = answer.version;
          }
        } catch {
          // The engine went away, or the document did: the catalog says which; ask again after the pause.
        }
        const early = VERSION_PACE_MS - (performance.now() - asked);
        if (early > 0) await pause(early, signal);
      }
    })().catch(() => {});
    return () => controller.abort();
  }, [client, file]);
}
