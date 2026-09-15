import { StrictMode, useSyncExternalStore } from "react";
import { createRoot } from "react-dom/client";
import {
  createHttpTessellationCacheProvider,
  setTessellationCacheProvider,
} from "cadgen-js/lib/surf/tessellationCache";
import CadWorkspace from "./components/CadWorkspace";
import faviconUrl from "./assets/favicon.ico";
import "./styles/globals.css";
import { getCadManifestSnapshot, subscribeCadManifest } from "./workbench/cadManifestStore.js";
import { applyTutorialTipResetQueryParam } from "./workbench/persistence.js";
import { DOCUMENT_TITLE } from "./workbench/constants.js";

const ROOT_ID = "root";
const ROOT_CACHE_KEY = "__cadViewerRoot";

function ensureFavicon() {
  if (typeof document === "undefined") {
    return;
  }

  let icon = document.querySelector('link[rel="icon"]');
  if (!icon) {
    icon = document.createElement("link");
    icon.rel = "icon";
    document.head.appendChild(icon);
  }
  icon.type = "image/x-icon";
  icon.href = `${faviconUrl}?v=star-tile`;
}

function bootstrap() {
  const rootElement = document.getElementById(ROOT_ID);
  if (!rootElement) {
    throw new Error(`Missing #${ROOT_ID} mount point.`);
  }
  // The viewer consumes the shared immutable tessellation object/index store
  // (served by cadgen.viewer on /__tess_cache/):
  // component loads and LOD level re-tessellations resolve through it and
  // write back on miss, so tessellations persist across sessions and are
  // shared with snapshots and exports. Best-effort by construction — any
  // failure degrades to plain in-page tessellation. The POST guard header
  // rides every request; only the write-back POSTs need it, but it is
  // harmless on GETs and keeps the provider config to one line.
  setTessellationCacheProvider(
    createHttpTessellationCacheProvider({ headers: { "x-cadgen-viewer": "1" } }),
  );
  ensureFavicon();
  // Before anything renders, so a re-armed tip can fire on this page load.
  applyTutorialTipResetQueryParam();
  document.title = DOCUMENT_TITLE;
  const cachedRoot = globalThis[ROOT_CACHE_KEY];
  const root = cachedRoot?.element === rootElement && cachedRoot?.root
    ? cachedRoot.root
    : createRoot(rootElement);
  globalThis[ROOT_CACHE_KEY] = {
    element: rootElement,
    root
  };
  root.render(
    <StrictMode>
      <AppRoot />
    </StrictMode>,
  );
}

function AppRoot() {
  const { manifest, revision, catalogHydrated, catalogRefreshing, catalogError } = useSyncExternalStore(
    subscribeCadManifest,
    getCadManifestSnapshot,
    getCadManifestSnapshot,
  );

  return (
    <CadWorkspace
      manifestRevision={revision}
      manifestEntries={manifest.entries}
      catalogHydrated={catalogHydrated}
      catalogRefreshing={catalogRefreshing}
      catalogError={catalogError}
    />
  );
}

bootstrap();
