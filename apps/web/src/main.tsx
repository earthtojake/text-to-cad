import { FileText } from 'lucide-react';
import { EmptyState } from '@hardcore/ui/navigation';
import { StrictMode, useMemo } from 'react';
import { createRoot } from 'react-dom/client';
import { FileViewer, type FileSource } from '@hardcore/ui/file-viewer';
import { ViewerLoadingOverlay } from '@hardcore/ui/file-viewer/presentation';
import { createCadClient } from '@hardcore/core/client';
import { unavailablePromptContext } from '@hardcore/core/prompt';
import type { ViewerHost } from '@hardcore/ui/host';
import { createTabStore, useTabViewerState } from '@hardcore/ui/tab-store';
import { browserClipboard } from './host/clipboard';
import App, { useTabAppearance } from './App';
import ViewerBrand from './client/components/workbench/ViewerBrand.jsx';
import ViewerLinks from './client/components/workbench/ViewerLinks.jsx';
import { readCadParam, readDefaultCadParam } from './client/workbench/sidebar.js';
import { sessionTabRecord } from './persistence/tabRecord';
import faviconUrl from './client/assets/favicon.png';
import './client/styles/globals.css';

// The tab's one store, over this tab's sessionStorage: everything the viewer keeps lives in it,
// survives a reload and goes with the tab (`docs/storage.md`).
const tabStore = createTabStore(sessionTabRecord(window.sessionStorage));

/** Keep the existing file-tab presentation while its root identity is requested. */
function StartingView({ error }: { error?: Error }) {
  const file = readCadParam() || readDefaultCadParam() || null;
  const { state, onStateChange } = useTabViewerState(tabStore, 'starting');
  const source = useMemo<FileSource>(() => {
    const pending = <T,>(signal: AbortSignal): Promise<T> => new Promise((_, reject) => {
      if (error) { reject(error); return; }
      if (signal.aborted) { reject(signal.reason); return; }
      signal.addEventListener('abort', () => reject(signal.reason), { once: true });
    });
    return { id: 'starting', rootName: 'This directory', stat: (_path, {signal}) => pending(signal), list: (_path, {signal}) => pending(signal) };
  }, [error]);
  const { colorScheme } = useTabAppearance(tabStore);
  const host = useMemo<ViewerHost>(() => ({
    files: source, clipboard: browserClipboard, promptContext: unavailablePromptContext,
    navigation: { openFile: () => {} }, environment: { colorScheme },
  }), [source, colorScheme]);
  return <div className="flex h-svh flex-col overflow-hidden"><div className="min-h-0 flex-1">
    <FileViewer leading={<ViewerBrand />} navigationActions={<ViewerLinks />} file={file} host={host} renderers={[]} state={state} onStateChange={onStateChange} navigationPath={null}
      presentation={{loading:<div className="relative h-full"><ViewerLoadingOverlay viewerLoading /></div>, error:() => <div className="relative h-full"><EmptyState icon={FileText} title="No file open" description="Pick one from the tree on the right, or filter by name." /></div>}} />
  </div></div>;
}

const element = document.getElementById('root');
if (!element) throw new Error('Missing #root mount point.');
const root = createRoot(element);
const client = createCadClient({ origin: '', shouldPoll: () => document.visibilityState !== 'hidden' });
let icon = document.querySelector<HTMLLinkElement>('link[rel="icon"]');
if (!icon) { icon = document.createElement('link'); icon.rel = 'icon'; document.head.append(icon); }
icon.type = 'image/png'; icon.href = faviconUrl;
document.title = 'text-to-cad';
const controller = new AbortController();
function dispose() { controller.abort(); root.unmount(); client.dispose(); window.removeEventListener('pagehide', onPageHide); }
function onPageHide(event: PageTransitionEvent) { if (!event.persisted) dispose(); }
window.addEventListener('pagehide', onPageHide);
if (import.meta.hot) import.meta.hot.dispose(dispose);
root.render(<StartingView />);
void client.serverInfo({ signal: controller.signal }).then(server => {
  if (controller.signal.aborted) return;
  if (typeof server.rootId !== 'string' || !server.rootId) throw new Error('The CAD service did not identify its file root.');
  root.render(<StrictMode><App client={client} server={server} tabStore={tabStore} /></StrictMode>);
}).catch(error => {
  if (!controller.signal.aborted) root.render(<StartingView error={error} />);
});
