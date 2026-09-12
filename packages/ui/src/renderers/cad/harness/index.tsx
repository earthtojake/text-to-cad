import { createRoot } from 'react-dom/client';
import { useState } from 'react';
import { FileViewer } from '@hardcore/ui/file-viewer';
import type { FileSource, FileViewerState } from '@hardcore/ui/file-viewer';
import { createCadClient } from '@hardcore/core/client';
import { createCadPreferences, createCadRenderer } from '@hardcore/ui/renderers/cad';
import type { CadCommands } from '@hardcore/ui/renderers/cad';

const captures: { file: string; size: number; type: string; references: unknown }[] = [];
const preferences = createCadPreferences();
function workspace(id: string) {
  let snapshot: CadCommands = {};
  const listeners = new Set<() => void>();
  const commands = {
    getSnapshot: () => snapshot,
    subscribe(listener: () => void) { listeners.add(listener); return () => { listeners.delete(listener); }; }
  };
  const capture = () => { snapshot = { captureRequest: { key: Date.now() } }; for (const listener of listeners) listener(); };
  const client = createCadClient({ origin: `${location.origin}/${id}`, workspaceId: id, pollIntervalMs: 0 });
  const source: FileSource = {
    id, rootName: id,
    stat: async (path) => ({ path, name: path, kind: 'file', size: 400, extension: 'stl' }),
    list: async () => [{ path: 'part.stl', name: 'part.stl', kind: 'file' }]
  };
  const renderers = [createCadRenderer({ client, preferences, commands, onCapture: ({ blob, file, references }) => captures.push({ file, size: blob.size, type: blob.type, references }) })];
  return { client, source, renderers, capture };
}
const a = workspace('one'), b = workspace('two');
function App() {
  const [state, setState] = useState<FileViewerState>({ panel: '', panelWidth: 300 });
  const [otherState, setOtherState] = useState<FileViewerState>({ panel: '', panelWidth: 300 });
  const [second, setSecond] = useState(false);
  const [mounted, setMounted] = useState(true);
  Object.assign(window, { cadHarness: { state, otherState, preferences, captures, capture: a.capture, second: setSecond, mounted: setMounted } });
  return <div style={{ display: 'flex', width: '1200px', height: '720px' }}>
    <section data-testid="one" style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column' }}>
      {mounted && <FileViewer file="part.stl" source={a.source} renderers={a.renderers} state={state} onStateChange={setState} onOpenFile={() => {}} />}
    </section>
    {second && <section data-testid="two" style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column' }}>
      <FileViewer file="part.stl" source={b.source} renderers={b.renderers} state={otherState} onStateChange={setOtherState} onOpenFile={() => {}} />
    </section>}
  </div>;
}
createRoot(document.getElementById('root')!).render(<App />);
