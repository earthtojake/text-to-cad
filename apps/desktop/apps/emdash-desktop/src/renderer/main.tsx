import {
  connectSession,
  createChatContext,
  createChatState,
  createChatView,
  pinTopMode,
} from '@emdash/chat-ui';
import ReactDOM from 'react-dom/client';
import { installChatUiRuntime } from '@core/features/conversations/api/browser/chat/chat-ui-runtime';
import { configureDevPerfClient } from '@core/features/dev-perf/api/browser/client';
import { installMonacoFacetBinder } from '@core/features/editor/browser/monaco/install-monaco-facet-binder';
import { monacoBootstrap } from '@core/features/editor/browser/monaco/monaco-bootstrap';
import { getProjectManagerStore } from '@core/features/projects/api/browser/stores/project-selectors';
import { prefetchAppSettingsKey } from '@core/features/settings/api/browser/use-app-settings-key';
import { initSoundPlayer, soundPlayer } from '@core/features/settings/browser/sound-player';
import { getSidebarStore } from '@core/features/workbench/contributions/browser/app-stores';
import { workbenchSidebarMemento } from '@core/features/workbench/contributions/mementos';
import { appStoreContributions } from '@core/manifests/browser/app-scoped-stores';
import { featureViewRuntimes } from '@core/manifests/browser/browser-contributions';
import { viewCatalog } from '@core/manifests/browser/view-catalog';
import { mementoCatalog } from '@core/manifests/shared/memento-catalog';
import { log } from '@core/primitives/logging/browser/logger';
import { getMementosWireClient } from '@core/primitives/mementos/api/client';
import { configureMementos, initMementos } from '@core/primitives/mementos/browser';
import '@fontsource-variable/ibm-plex-sans/index.css';
import '@emdash/ui/style.css';
import '@emdash/ui/react/chat-ui/chat-theme.css';
import '@emdash/chat-ui/style.css';
import './index.css';
import 'devicon/devicon.min.css';
import 'katex/dist/katex.min.css';
// Load the canonical product tokens after inherited structural styles.
import './design-system.css';
import { MementoClientProvider, SubjectProvider } from '@core/primitives/mementos/react';
import {
  workbenchHistoryMemento,
  workbenchNavigationMemento,
} from '@core/primitives/navigation/api/mementos';
import { getNavigation } from '@core/primitives/navigation/browser/navigation-selectors';
import { createAppScope } from '@core/primitives/scoped-stores/browser';
import { appSubject } from '@core/primitives/subjects/api';
import { assertViewRuntimesComplete, registerViewRuntime } from '@core/primitives/views/react';
import { ErrorBoundary } from '@renderer/error-boundary';
import {
  dismissBootSplash,
  initBootSplash,
  showBootSplashEscapeHatch,
} from '@renderer/lib/boot/boot-splash';
import {
  raceSplashGate,
  SPLASH_GATE_TIMEOUT_MS,
  waitForActiveProjectContext,
} from '@renderer/lib/boot/splash-gate';
import { wireExternalLinkRequests } from '@renderer/lib/external-link-requests';
import { getDesktopWireClient } from '@renderer/lib/runtime/desktop-wire-client';
import { seedDesktopWire } from '@renderer/lib/runtime/seed-desktop-wire';
import { seedRendererNavigationHost } from '@renderer/lib/runtime/seed-navigation-host';
import { initRendererPerfVitals } from '@renderer/utils/perf-vitals';
import { initNotificationDeliveryListener } from '@root/src/core/services/notifications/browser';
import { App } from './App';
import { wireNavigationTelemetry } from './lib/stores/navigation-telemetry';

const bootstrapStartedAt = performance.now();
let lastBootMarkAt = bootstrapStartedAt;
function bootMark(mark: string, extra?: Record<string, unknown>): void {
  const now = performance.now();
  log.info('boot-timeline renderer', {
    mark,
    sincePageStartMs: Math.round(now),
    sinceBootstrapMs: Math.round(now - bootstrapStartedAt),
    sincePreviousMarkMs: Math.round(now - lastBootMarkAt),
    ...extra,
  });
  lastBootMarkAt = now;
}

async function bootstrap() {
  bootMark('bootstrap-start');
  // The static splash from index.html is already painted; wire its watchdog
  // escape hatch before anything that could block.
  initBootSplash();
  // Core owns wire access through the seeded-connection seam; seed it before
  // React mounts so any slice can reach the wire without host imports.
  seedDesktopWire();

  // Navigation lives in core behind a seeded host seam; the bootstrap hands it
  // the aggregated view catalog before the app scope creates the stores.
  seedRendererNavigationHost();

  installChatUiRuntime({
    connectSession,
    createChatContext,
    createChatState,
    createChatView,
    pinTopMode,
  });
  wireExternalLinkRequests();

  // Builds and activates all app-scoped stores (projects, machines, sidebar,
  // updates) before React mounts.
  createAppScope([...appStoreContributions]);
  // Give the app-global OpenFileStore its Monaco implementation before any
  // file tab can acquire facets (handle creation awaits Monaco internally).
  installMonacoFacetBinder();
  // Monaco starts first but is never awaited before render: facet handles
  // resolve it internally, so editors opened in the first second still work.
  void monacoBootstrap
    .init()
    .catch((error: unknown) => {
      log.warn('[monaco-bootstrap] init failed:', error);
    })
    .then(() => bootMark('monaco-ready'));
  initSoundPlayer();
  initNotificationDeliveryListener((sound, dedupeKey) => soundPlayer.play(sound, dedupeKey));
  initRendererPerfVitals();
  configureDevPerfClient(async () => (await getDesktopWireClient()).devPerf);

  // Stores may acquire memento spaces while project data loads, so initialize
  // the singleton before starting any store construction.
  configureMementos({
    getWireClient: getMementosWireClient,
    catalog: mementoCatalog,
    onError: (error) => log.error('Memento operation failed:', error),
  });
  const mementoClient = await initMementos();
  bootMark('mementos-initialized');

  void prefetchAppSettingsKey('interface');
  void prefetchAppSettingsKey('browser');

  for (const contribution of featureViewRuntimes) registerViewRuntime(contribution);
  assertViewRuntimesComplete(viewCatalog);

  const appSpace = mementoClient.subject(appSubject({}));
  const historyHandle = appSpace.handle(workbenchHistoryMemento);
  const legacyNavigationHandle = appSpace.handle(workbenchNavigationMemento);
  const sidebarHandle = appSpace.handle(workbenchSidebarMemento);
  // Memento reads queue behind the wire until the backend registers its
  // controllers, so navigation restore is a gate condition rather than a
  // render prerequisite. On the timeout path the restore lands after render;
  // the stores are observable, so the last-active view snaps in when ready.
  const navigationRestored = appSpace.ready.then(() => {
    bootMark('memento-handles-ready');
    getNavigation().attachMemento(historyHandle, legacyNavigationHandle);
    getSidebarStore().attachMemento(sidebarHandle);
    if (!sidebarHandle.hasStoredValue) getSidebarStore().expandAllProjects();
    wireNavigationTelemetry(getNavigation());
  });

  // The list snapshot resolves load(); Host attachment may continue in the
  // background. The gate below awaits only desktop context for the Project
  // required by the restored view.
  const projectsLoaded = getProjectManagerStore()
    .load()
    .then(() => bootMark('projects-loaded'));
  const activeProjectReady = waitForActiveProjectContext({
    navigationRestored,
    projectsLoaded,
    activeProjectId: () => {
      const ref = getNavigation().currentRef;
      return ref.viewId === 'project' || ref.viewId === 'task'
        ? (ref.params as { projectId?: string }).projectId
        : undefined;
    },
    hydrateProjectContext: (projectId) => getProjectManagerStore().hydrateProjectContext(projectId),
  });

  const gate = raceSplashGate([navigationRestored, activeProjectReady], SPLASH_GATE_TIMEOUT_MS);

  // Render immediately behind the splash; the gate only decides when the
  // splash lifts. Avoid double-mount in dev which can duplicate PTY sessions.
  ReactDOM.createRoot(document.getElementById('root') as HTMLElement).render(
    <ErrorBoundary>
      <MementoClientProvider client={mementoClient}>
        <SubjectProvider subject={appSubject({})}>
          <App />
        </SubjectProvider>
      </MementoClientProvider>
    </ErrorBoundary>
  );
  bootMark('react-render-called');

  const outcome = await gate;
  dismissBootSplash();
  bootMark('app-content-ready', { gate: outcome });
  window.electronAPI.reportBootUsable();
}

bootstrap().catch((error: unknown) => {
  log.error('Renderer bootstrap failed:', error);
  // A fatal bootstrap error leaves nothing behind the splash; surface the
  // escape hatch so the user can restart or reach recovery.
  showBootSplashEscapeHatch();
});
