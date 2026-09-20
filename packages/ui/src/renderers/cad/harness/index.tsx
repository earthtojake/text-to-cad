import { createRoot } from 'react-dom/client';
import { useState } from 'react';
import { FileViewer } from '@hardcore/ui/file-viewer';
import type { FileSource, FileViewerState } from '@hardcore/ui/file-viewer';
import { createCadClient } from '@hardcore/core/client';
import { createCadPreferences, createCadRenderer } from '@hardcore/ui/renderers/cad';
import type { ViewerHost } from '@hardcore/ui/host';
import type { CadLiveController, CadCommands } from '@hardcore/ui/renderers/cad';

const captures: { file: string; size: number; type: string; references: unknown }[] = [];
const preferences = createCadPreferences();
function workspace(id: string) {
  let snapshot: CadCommands = {};
  const listeners = new Set<() => void>();
  const commands = {
    getSnapshot: () => snapshot,
    acknowledge(kind: keyof CadCommands, key: string | number) {
      if (snapshot[kind]?.key !== key) return;
      snapshot = { ...snapshot, [kind]: null };
      for (const listener of listeners) listener();
    },
    subscribe(listener: () => void) { listeners.add(listener); return () => { listeners.delete(listener); }; }
  };
  const capture = () => { snapshot = { captureRequest: { key: Date.now() } }; for (const listener of listeners) listener(); };
  const client = createCadClient({ origin: `${location.origin}/${id}`, workspaceId: id, pollIntervalMs: 0 });
  const source: FileSource = {
    id, rootName: id,
    stat: async (path) => ({ path, name: path, kind: 'file', size: 400, extension: 'stl' }),
    list: async () => [{ path: 'part.stl', name: 'part.stl', kind: 'file' }]
  };
  const destination = { kind: 'composer' as const, available: true };
  const host: ViewerHost = { files: source, navigation: { openFile() {} }, environment: { colorScheme: 'dark' },
    clipboard: { writeText: async () => {}, readText: async () => '', writeImage: async () => {} },
    promptContext: { getSnapshot: () => destination, subscribe: () => () => {}, deliver: async context => {
      const attachment = context.parts.find(part => part.kind === 'attachment');
      if (attachment?.kind === 'attachment') { const blob = await attachment.content; captures.push({ file: 'part.stl', size: blob.size, type: blob.type, references: context.parts.filter(part => part.kind === 'reference').map(part => part.reference) }); }
      return { status: 'added', partIds: context.parts.map(part => part.id) };
    } }
  };
  let controller: CadLiveController | null = null;
  const live = { bind(next: CadLiveController) { controller = next; return () => { controller = null; }; } };
  const renderers = [createCadRenderer({ client, preferences, commands, live })];
  return { client, source, host, renderers, capture, get controller() { return controller; } };
}
const a = workspace('one'), b = workspace('two');
// Directory navigation hydrates before a renderer mounts. Large workspaces
// return path-only placeholders until the selected file is requested.
await Promise.all([a.client.refresh(), b.client.refresh()]);
function App() {
  const [state, setState] = useState<FileViewerState>({ panel: '', panelWidth: 300 });
  const [otherState, setOtherState] = useState<FileViewerState>({ panel: '', panelWidth: 300 });
  const [second, setSecond] = useState(false);
  const [mounted, setMounted] = useState(true);
  const [fullscreen, setFullscreen] = useState(false);
  Object.assign(window, { cadHarness: { a, b, state, otherState, preferences, captures, capture: a.capture, second: setSecond, mounted: setMounted, fullscreen: setFullscreen } });
  return <div style={{ display: 'flex', width: '1200px', height: '720px' }}>
    <section data-testid="one" style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column' }}>
      {mounted && <FileViewer fullscreen={fullscreen} onExitFullscreen={() => setFullscreen(false)} file="part.stl" host={a.host} renderers={a.renderers} state={state} onStateChange={setState} />}
    </section>
    {second && <section data-testid="two" style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column' }}>
      <FileViewer file="part.stl" host={b.host} renderers={b.renderers} state={otherState} onStateChange={setOtherState} />
    </section>}
  </div>;
}
createRoot(document.getElementById('root')!).render(<App />);
