import { FileWarning } from 'lucide-react';
import { EmptyState } from '@text-to-cad/ui/navigation';
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { createCrashReporter, isEngineGone } from '@text-to-cad/core/client';
import { ViewerLoadingOverlay } from '@text-to-cad/ui/file-viewer/presentation';
import { createTabStore } from '@text-to-cad/ui/tab-store';
import { I18nProvider, resolveLocale, translateIn } from '@text-to-cad/ui/i18n';
import { createWebCadClient } from './host/cadClient.js';
import App from './App';
import { EngineStopped } from './EngineStopped';
import { sessionTabRecord } from './persistence/tabRecord';
import faviconUrl from './client/assets/favicon.png';
import './client/styles/globals.css';

// The tab's one store, over this tab's sessionStorage: everything the viewer keeps lives in it,
// survives a reload and goes with the tab (`docs/storage.md`).
const tabStore = createTabStore(sessionTabRecord(window.sessionStorage));

/** What the page shows while it asks the server what it is, and if the server does not answer. */
function StartingView({ error }: { error?: Error }) {
  // Before the server answers there is no kept choice to read: the browser's language.
  const locale = resolveLocale(navigator.languages ?? [navigator.language]);
  return <I18nProvider locale={locale}><div className="relative h-svh overflow-hidden bg-background">{error && isEngineGone(error)
    ? <EngineStopped locale={locale} />
    : error ? <EmptyState icon={FileWarning} title={translateIn(locale, 'app.start.notAnswering')} description={error.message} tone="warn" />
    : <ViewerLoadingOverlay viewerLoading />}</div></I18nProvider>;
}

const element = document.getElementById('root');
if (!element) throw new Error('Missing #root mount point.');
// The catalog is read every two seconds while the tab is seen: a hidden tab asks nothing and is read
// again the moment it is shown (`host/cadClient.js`).
const client = createWebCadClient();
// The page's crashes -- an error nothing caught, or one a view's boundary caught -- told to this
// Viewer's server for its telemetry (`cadgen/analytics.py`), each once a page and never its message.
const reportCrash = createCrashReporter(crash => client.reportActivity({ crash }));
const onError = (event: ErrorEvent) => reportCrash(event.error);
const onRejection = (event: PromiseRejectionEvent) => reportCrash(event.reason);
window.addEventListener('error', onError);
window.addEventListener('unhandledrejection', onRejection);
const root = createRoot(element, {
  // Logged as React logs one, and counted: the page went on, with the view's "could not display".
  onCaughtError: (error, info) => { console.error(error, info.componentStack); reportCrash(error, { handled: true }); },
});
let icon = document.querySelector<HTMLLinkElement>('link[rel="icon"]');
if (!icon) { icon = document.createElement('link'); icon.rel = 'icon'; document.head.append(icon); }
icon.type = 'image/png'; icon.href = faviconUrl;
document.title = 'CAD';
const controller = new AbortController();
function dispose() {
  controller.abort(); root.unmount(); client.dispose(); window.removeEventListener('pagehide', onPageHide);
  window.removeEventListener('error', onError); window.removeEventListener('unhandledrejection', onRejection);
}
function onPageHide(event: PageTransitionEvent) { if (!event.persisted) dispose(); }
window.addEventListener('pagehide', onPageHide);
if (import.meta.hot) import.meta.hot.dispose(dispose);
root.render(<StartingView />);
// The update notice comes with the server's description, so the update button draws with the page.
// So is the person's language, so the page's first paint is in it.
void Promise.all([client.serverInfo({ signal: controller.signal }), client.version().then(reply => reply.notice ?? null, () => null),
  client.language().then(reply => reply.locale, () => null)]).then(([server, notice, language]) => {
  if (controller.signal.aborted) return;
  root.render(<StrictMode><App client={client} server={server} tabStore={tabStore} notice={notice} language={language} /></StrictMode>);
}).catch(error => {
  if (!controller.signal.aborted) root.render(<StartingView error={error} />);
});
