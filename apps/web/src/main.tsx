import { FileWarning } from 'lucide-react';
import { EmptyState } from '@text-to-cad/ui/navigation';
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { ViewerLoadingOverlay } from '@text-to-cad/ui/file-viewer/presentation';
import { createTabStore } from '@text-to-cad/ui/tab-store';
import { createWebCadClient } from './host/cadClient.js';
import App from './App';
import { sessionTabRecord } from './persistence/tabRecord';
import faviconUrl from './client/assets/favicon.png';
import './client/styles/globals.css';

// The tab's one store, over this tab's sessionStorage: everything the viewer keeps lives in it,
// survives a reload and goes with the tab (`docs/storage.md`).
const tabStore = createTabStore(sessionTabRecord(window.sessionStorage));

/** What the page shows while it asks the server what it is, and if the server does not answer. */
function StartingView({ error }: { error?: Error }) {
  return <div className="relative h-svh overflow-hidden bg-background">{error
    ? <EmptyState icon={FileWarning} title="The CAD Viewer is not answering" description={error.message} tone="warn" />
    : <ViewerLoadingOverlay viewerLoading />}</div>;
}

const element = document.getElementById('root');
if (!element) throw new Error('Missing #root mount point.');
const root = createRoot(element);
// The catalog is read every two seconds while the tab is seen: a hidden tab asks nothing and is read
// again the moment it is shown (`host/cadClient.js`).
const client = createWebCadClient();
let icon = document.querySelector<HTMLLinkElement>('link[rel="icon"]');
if (!icon) { icon = document.createElement('link'); icon.rel = 'icon'; document.head.append(icon); }
icon.type = 'image/png'; icon.href = faviconUrl;
document.title = 'CAD';
const controller = new AbortController();
function dispose() { controller.abort(); root.unmount(); client.dispose(); window.removeEventListener('pagehide', onPageHide); }
function onPageHide(event: PageTransitionEvent) { if (!event.persisted) dispose(); }
window.addEventListener('pagehide', onPageHide);
if (import.meta.hot) import.meta.hot.dispose(dispose);
root.render(<StartingView />);
// The update notice comes with the server's description, so the update button draws with the page.
void Promise.all([client.serverInfo({ signal: controller.signal }), client.version().then(reply => reply.notice ?? null, () => null)]).then(([server, notice]) => {
  if (controller.signal.aborted) return;
  root.render(<StrictMode><App client={client} server={server} tabStore={tabStore} notice={notice} /></StrictMode>);
}).catch(error => {
  if (!controller.signal.aborted) root.render(<StartingView error={error} />);
});
