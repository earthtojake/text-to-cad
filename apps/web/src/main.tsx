import { StrictMode, type ReactNode } from 'react';
import { createRoot } from 'react-dom/client';
import { createCrashReporter, openShare, openViewBundle, readShareAddress, viewBundleUrlSource } from '@cad/core/client';
import { createTabStore } from '@cad/ui/tab-store';
import { EmptyState } from '@cad/ui/navigation';
import { I18nProvider, resolveLocale, translateIn } from '@cad/ui/i18n';
import { createWebCadClient } from './host/cadClient.js';
import { keepAddressLink } from './host/addressLink.js';
import { reloadOnStaleBuild } from './host/staleBuild.js';
import { browserLanguage } from './host/browserLanguage.js';
import App from './App';
import BundleApp from './BundleApp';
import { ShareDelete, ShareFailed } from './SharePage';
import { shareService } from './host/share.js';
import { readDocumentId } from './client/workbench/fileParam.js';
import { readBundleAddress } from './client/workbench/bundleParam.js';
import { StartingView } from './StartingView';
import { sessionTabRecord } from './persistence/tabRecord';
import faviconUrl from './client/assets/favicon.png';
import './client/styles/globals.css';

// The tab's one store, over this tab's sessionStorage: everything the viewer keeps lives in it,
// survives a reload and goes with the tab (`docs/storage.md`).
const tabStore = createTabStore(sessionTabRecord(window.sessionStorage));

const element = document.getElementById('root');
if (!element) throw new Error('Missing #root mount point.');
let icon = document.querySelector<HTMLLinkElement>('link[rel="icon"]');
if (!icon) { icon = document.createElement('link'); icon.rel = 'icon'; document.head.append(icon); }
icon.type = 'image/png'; icon.href = faviconUrl;
document.title = 'text-to-cad';
// A chunk of the build this page was served, gone from the server since (a new release, a rebuilt bundle):
// the page reloads into the build the server has now, rather than a view saying it could not display.
const stopStaleBuild = reloadOnStaleBuild();

// The page is the engine's, or it shows one view bundle (its address's `?bundle=`), or a shared one (a share
// service's `/<id>`, or its delete page, `/<id>#delete=<secret>`): chosen here, once.
const share = readShareAddress(window.location.href);
let bundle: string | null = null;
let refused: Error | null = null;
if (!share) {
  try { bundle = readBundleAddress(); } catch (error) { refused = error instanceof Error ? error : new Error(String(error)); }
}
if (share) startShare(element, share);
else if (bundle !== null || refused) startViewBundle(element, bundle, refused);
else startEngine(element);

/** The engine's page: one document at a time by its id, or the home, read from the server that served it. */
function startEngine(element: HTMLElement) {
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
  const root = createRoot(element, {
    // Logged as React logs one, and counted: the page went on, with the view's "could not display".
    onCaughtError: (error, info) => { console.error(error, info.componentStack); reportCrash(error, { handled: true }); },
  });
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
}

/**
 * A view bundle's page: the bundle's one document, read from its folder on this page's own server and from
 * nothing else (`BundleApp`). Until its manifest is read the page is the bar `index.html` drew; a bundle that
 * cannot be opened says why, in the browser's language or the one the person chose here.
 */
function startViewBundle(element: HTMLElement, address: string | null, refused: Error | null) {
  const root = createRoot(element, { onCaughtError: (error, info) => { console.error(error, info.componentStack); } });
  const controller = new AbortController();
  let client: Awaited<ReturnType<typeof openViewBundle>> | null = null;
  function dispose() { controller.abort(); stopStaleBuild(); root.unmount(); client?.dispose(); window.removeEventListener('pagehide', onPageHide); }
  function onPageHide(event: PageTransitionEvent) { if (!event.persisted) dispose(); }
  window.addEventListener('pagehide', onPageHide);
  if (import.meta.hot) import.meta.hot.dispose(dispose);
  const said = browserLanguage();
  const failed = (error: unknown, language: string | null) => {
    const locale = language ?? resolveLocale(navigator.languages ?? [navigator.language]);
    root.render(<I18nProvider locale={locale}><div className="fixed inset-0 overflow-hidden bg-background">
      <EmptyState title={translateIn(locale, 'file.openFailed')} description={error instanceof Error ? error.message : String(error)} />
    </div></I18nProvider>);
  };
  void said().then(reply => reply.locale, () => null).then(async language => {
    if (refused || !address) { failed(refused, language); return; }
    try {
      client = await openViewBundle(viewBundleUrlSource(address), { signal: controller.signal });
    } catch (error) {
      if (!controller.signal.aborted) failed(error, language);
      return;
    }
    if (controller.signal.aborted) { client.dispose(); return; }
    root.render(<StrictMode><BundleApp client={client} tabStore={tabStore} language={language} /></StrictMode>);
  });
}

/**
 * A shared view bundle's page, as a share service serves it at `/<id>`: the view reads the share's manifest and
 * its packs from this page's own origin (`shareService`), opens them with the key its id gives (`openShare`) and
 * shows the bundle as `?bundle=` does (`BundleApp`); the delete link (`#delete=<secret>`) is the page that deletes
 * it (`ShareDelete`). The secret is read from the address once, here, and is never written anywhere: not to the
 * address or its history, storage, a log or a request but the DELETE's header. Until the share opens the page is
 * the bar `index.html` drew.
 */
function startShare(element: HTMLElement, address: NonNullable<ReturnType<typeof readShareAddress>>) {
  const root = createRoot(element, { onCaughtError: (error, info) => { console.error(error, info.componentStack); } });
  const controller = new AbortController();
  let client: Awaited<ReturnType<typeof openShare>> | null = null;
  function dispose() { controller.abort(); stopStaleBuild(); root.unmount(); client?.dispose(); window.removeEventListener('pagehide', onPageHide); }
  function onPageHide(event: PageTransitionEvent) { if (!event.persisted) dispose(); }
  window.addEventListener('pagehide', onPageHide);
  if (import.meta.hot) import.meta.hot.dispose(dispose);
  void browserLanguage()().then(reply => reply.locale, () => null).then(language => {
    const locale = language ?? resolveLocale(navigator.languages ?? [navigator.language]);
    const page = (node: ReactNode) => root.render(<I18nProvider locale={locale}>{node}</I18nProvider>);
    if ('deleteSecret' in address) { page(<ShareDelete id={address.id} secret={address.deleteSecret} locale={locale} />); return; }
    const { id } = address;
    const open = async () => {
      page(<div aria-hidden="true" data-boot-navbar="" />);
      try {
        client = await openShare(id, shareService(id), { signal: controller.signal });
      } catch (error) {
        if (!controller.signal.aborted) page(<ShareFailed error={error} locale={locale} onRetry={() => void open()} />);
        return;
      }
      if (controller.signal.aborted) { client.dispose(); return; }
      root.render(<StrictMode><BundleApp client={client} tabStore={tabStore} language={language} /></StrictMode>);
    };
    void open();
  });
}
