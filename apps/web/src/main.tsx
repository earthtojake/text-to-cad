import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { createCrashReporter } from '@cad/core/client';
import { createTabStore } from '@cad/ui/tab-store';
import { createWebCadClient } from './host/cadClient.js';
import { keepAddressLink } from './host/addressLink.js';
import { reloadOnStaleBuild } from './host/staleBuild.js';
import App from './App';
import { readDocumentId } from './client/workbench/fileParam.js';
import { StartingView } from './StartingView';
import { sessionTabRecord } from './persistence/tabRecord';
import faviconUrl from './client/assets/favicon.png';
import './client/styles/globals.css';

// The tab's one store, over this tab's sessionStorage: everything the viewer keeps lives in it,
// survives a reload and goes with the tab (`docs/storage.md`).
const tabStore = createTabStore(sessionTabRecord(window.sessionStorage));

const element = document.getElementById('root');
if (!element) throw new Error('Missing #root mount point.');
// The catalog is read every two seconds while the tab is seen: a hidden tab asks nothing and is read
// again the moment it is shown (`host/cadClient.js`).
const client = createWebCadClient();
// The address keeps a working link, so it opens this page in another browser on this machine too.
const stopAddressLink = keepAddressLink({ fetchLink: () => client.link() });
// The page's crashes -- an error nothing caught, or one a view's boundary caught -- told to this
// Viewer's server for its telemetry (`cad_server/analytics.py`), each once a page and never its message.
const reportCrash = createCrashReporter(crash => client.reportActivity({ crash }));
const onError = (event: ErrorEvent) => reportCrash(event.error);
const onRejection = (event: PromiseRejectionEvent) => reportCrash(event.reason);
window.addEventListener('error', onError);
window.addEventListener('unhandledrejection', onRejection);
// A chunk of the build this page was served, gone from the server since (a new release, a rebuilt bundle):
// the page reloads into the build the server has now, rather than a view saying it could not display.
const stopStaleBuild = reloadOnStaleBuild();
const root = createRoot(element, {
  // Logged as React logs one, and counted: the page went on, with the view's "could not display".
  onCaughtError: (error, info) => { console.error(error, info.componentStack); reportCrash(error, { handled: true }); },
});
let icon = document.querySelector<HTMLLinkElement>('link[rel="icon"]');
if (!icon) { icon = document.createElement('link'); icon.rel = 'icon'; document.head.append(icon); }
icon.type = 'image/png'; icon.href = faviconUrl;
document.title = 'text-to-cad';
const controller = new AbortController();
function dispose() {
  controller.abort(); stopAddressLink(); stopStaleBuild(); root.unmount(); client.dispose(); window.removeEventListener('pagehide', onPageHide);
  window.removeEventListener('error', onError); window.removeEventListener('unhandledrejection', onRejection);
}
function onPageHide(event: PageTransitionEvent) { if (!event.persisted) dispose(); }
window.addEventListener('pagehide', onPageHide);
if (import.meta.hot) import.meta.hot.dispose(dispose);
// The app's frame from the first paint (`StartingView`: the file viewer in its opening phase), while the server says
// what it is.
root.render(<StartingView tabStore={tabStore} />);
// The document the URL names is asked for beside the description, into the client's catalog, so its
// page's first frame has its name where the server says it in time; the paint never waits for it
// (a slow answer, a document that is gone): its name's place stays empty until the catalog answers.
const opening = readDocumentId();
// Unsignalled, so the catalog read the page starts with shares this request (`client.refresh`).
if (opening) void client.resolveEntry(opening).catch(() => {});
// The person's language comes with the server's description, so the page's first paint is in it.
void Promise.all([client.serverInfo({ signal: controller.signal }),
  client.language().then(reply => reply.locale, () => null)]).then(([server, language]) => {
  if (controller.signal.aborted) return;
  root.render(<StrictMode><App client={client} server={server} tabStore={tabStore} language={language} /></StrictMode>);
}).catch(error => {
  if (!controller.signal.aborted) root.render(<StartingView error={error} tabStore={tabStore} />);
});
