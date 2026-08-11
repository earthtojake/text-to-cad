import { StrictMode, useSyncExternalStore } from "react";
import { createRoot } from "react-dom/client";
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
  const { manifest, revision, catalogHydrated, catalogRefreshing, catalogError, activeDir } = useSyncExternalStore(
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
      activeDir={activeDir}
    />
  );
}

bootstrap();
