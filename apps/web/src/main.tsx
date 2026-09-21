import { FileText } from 'lucide-react';
import { EmptyState } from '@hardcore/ui/navigation';
import { StrictMode, useMemo, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { FileViewer, type FileSource } from '@hardcore/ui/file-viewer';
import { ViewerLoadingOverlay } from '@hardcore/ui/file-viewer/presentation';
import { createCadClient } from '@hardcore/core/client';
import { unavailablePromptContext } from '@hardcore/core/prompt';
import type { ViewerHost } from '@hardcore/ui/host';
import { browserClipboard } from './host/clipboard';
import { browserLifecycle } from './host/lifecycle';
import App from './App';
import ViewerTopBar from './client/components/workbench/ViewerTopBar.jsx';
import { readCadParam, readDefaultCadParam } from './client/workbench/sidebar.js';
import { readColorSchemePreference, resolveColorSchemeMode } from './client/ui/colorScheme.js';
import { readViewState } from './persistence/fileViewer';
import faviconUrl from './client/assets/favicon.ico';
import './client/styles/globals.css';

/** Keep the existing file-tab presentation while its root identity is requested. */
function StartingView({ error }: { error?: Error }) {
  const file = readCadParam() || readDefaultCadParam() || null;
  const [state, setState] = useState(() => readViewState('starting'));
  const source = useMemo<FileSource>(() => {
    const pending = <T,>(signal: AbortSignal): Promise<T> => new Promise((_, reject) => {
      if (error) { reject(error); return; }
      if (signal.aborted) { reject(signal.reason); return; }
      signal.addEventListener('abort', () => reject(signal.reason), { once: true });
    });
    return { id: 'starting', rootName: 'This directory', stat: (_path, {signal}) => pending(signal), list: (_path, {signal}) => pending(signal) };
  }, [error]);
  const dark = resolveColorSchemeMode(readColorSchemePreference(), { prefersDark: matchMedia('(prefers-color-scheme: dark)').matches }) === 'dark';
  const host = useMemo<ViewerHost>(() => ({
    files: source, clipboard: browserClipboard, promptContext: unavailablePromptContext,
    navigation: { openFile: () => {} }, environment: { colorScheme: dark ? 'dark' : 'light' }, lifecycle: browserLifecycle,
  }), [source, dark]);
  return <div className="flex h-svh flex-col overflow-hidden"><ViewerTopBar /><div className="min-h-0 flex-1">
    <FileViewer file={file} host={host} renderers={[]} state={state} onStateChange={setState} navigationPath={null} narrowCrumbs={false}
      presentation={{loading:<div className="relative h-full"><ViewerLoadingOverlay viewerLoading /></div>, error:() => <div className="relative h-full"><EmptyState icon={FileText} title="No file open" description="Pick one from the tree on the right, or filter by name." /></div>}} />
  </div></div>;
}

const element = document.getElementById('root');
if (!element) throw new Error('Missing #root mount point.');
const root = createRoot(element);
const client = createCadClient({ origin: '', shouldPoll: () => document.visibilityState !== 'hidden' });
let icon = document.querySelector<HTMLLinkElement>('link[rel="icon"]');
if (!icon) { icon = document.createElement('link'); icon.rel = 'icon'; document.head.append(icon); }
icon.type = 'image/x-icon'; icon.href = `${faviconUrl}?v=star-tile`;
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
  root.render(<StrictMode><App client={client} server={server} /></StrictMode>);
}).catch(error => {
  if (!controller.signal.aborted) root.render(<StartingView error={error} />);
});
