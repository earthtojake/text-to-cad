import { createRoot } from 'react-dom/client';
import { useCallback, useMemo, useState } from 'react';
import { unavailablePromptContext } from '@cad/core/prompt';
import { createCadClient } from '@cad/core/client';
import { CadViewer, createCadFileSource } from '@cad/ui/cad-viewer';
import { createLiveRegistry, type HomeLocation } from '@cad/ui/host';
import type { ModelLibrarySource } from '@cad/ui/library';
import { createTabStore, memoryTabRecord } from '@cad/ui/tab-store';

// The viewer a host composes (`CadViewer`), over the core client and the engine's API as the spec's server answers it
// (`CadViewer.browser.test.mjs`): the home, a project's folder, its documents and what a page records of each.
// The catalog of the file on screen read again every two seconds, as the web page's client reads it.
const client = createCadClient({ origin: location.origin, pollIntervalMs: 2000 });
const tabStore = createTabStore(memoryTabRecord());
const live = createLiveRegistry();
const host = { files: createCadFileSource(client), clipboard: { writeText: async () => {}, writeImage: async () => {} },
  promptContext: unavailablePromptContext, environment: { colorScheme: 'light' as const } };
// Every file the viewer asked the host to show, in order (`''` the home).
const shows: string[] = [];
const first = new URLSearchParams(location.search).get('file') || '';

function App() {
  const [file, setFile] = useState(first);
  const [place, setPlace] = useState<HomeLocation | undefined>(undefined);
  const onShow = useCallback((next: string, where?: HomeLocation) => { shows.push(next); setFile(next); if (!next) setPlace(where); }, []);
  // Once the catalog has the document, the page says it was opened now, as the web page does (`apps/web`'s `App`).
  const onShown = useCallback((path: string | null) => { if (path) void client.changeRecents({ action: 'open', path }).catch(() => {}); }, []);
  const library = useMemo<ModelLibrarySource>(() => ({
    list: () => client.recents(),
    change: (action, entry) => client.changeRecents({ action, path: entry.path }),
    thumbnail: async () => null,
    open: async entry => { onShow(entry.path); },
    projects: () => client.projects?.() ?? Promise.resolve([]),
    folder: (project, options) => client.projectFolder!(project, options),
  }), [onShow]);
  Object.assign(window, { cadHarness: { shows, show: onShow } });
  return <div style={{ width: '100vw', height: '100vh', display: 'flex', flexDirection: 'column' }}>
    <CadViewer client={client} host={host} tabStore={tabStore} live={live} file={file} onShow={onShow} onShown={onShown}
      place={place} library={library} />
  </div>;
}
await client.refresh().catch(() => {});
createRoot(document.getElementById('root')!).render(<App />);
