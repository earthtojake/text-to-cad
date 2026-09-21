import { createRoot } from 'react-dom/client';
import { useState } from 'react';
import { FileViewer } from '@hardcore/ui/file-viewer';
import type { FileSource, FileViewerState } from '@hardcore/ui/file-viewer';
import { createCadClient } from '@hardcore/core/client';
import { createCadPreferences } from '@hardcore/ui/renderers/workspace';
import { createStepRenderer } from '@hardcore/ui/renderers/step';
import { createDxfRenderer } from '@hardcore/ui/renderers/dxf';
import { createGlbRenderer } from '@hardcore/ui/renderers/glb';
import { createMeshRenderer } from '@hardcore/ui/renderers/mesh';
import { createRobotRenderer } from '@hardcore/ui/renderers/robot';
import { createHarnessRenderer } from '@hardcore/ui/renderers/shell-harness';
import type { ViewerHost } from '@hardcore/ui/host';
import type { CadLiveController, CadCommands } from '@hardcore/ui/renderers/step';

// The one file both panes open: `?file=arm.urdf` for a test whose fixture is not the default mesh.
const file = new URLSearchParams(location.search).get('file') || 'part.stl';
const captures: { file: string; size: number; type: string; references: unknown }[] = [];
// What a renderer asked the host to open (a mesh a robot description names, say).
const opened: string[] = [];
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
  const request = (next: CadCommands) => { snapshot = next; for (const listener of listeners) listener(); };
  const capture = () => request({ captureRequest: { key: Date.now() } });
  const selectReference = (selector: string) => request({ selectReference: { selector, key: Date.now() } });
  const client = createCadClient({ origin: `${location.origin}/${id}`, workspaceId: id, pollIntervalMs: 0 });
  const source: FileSource = {
    id, rootName: id,
    stat: async (path) => ({ path, name: path, kind: 'file', size: 400, extension: path.split('.').pop() || '' }),
    list: async () => [{ path: file, name: file, kind: 'file' }]
  };
  const destination = { kind: 'composer' as const, available: true };
  const host: ViewerHost = { files: source, navigation: { openFile(path) { opened.push(path); } }, environment: { colorScheme: 'dark' },
    clipboard: { writeText: async () => {}, readText: async () => '', writeImage: async () => {} },
    promptContext: { getSnapshot: () => destination, subscribe: () => () => {}, deliver: async context => {
      const attachment = context.parts.find(part => part.kind === 'attachment');
      if (attachment?.kind === 'attachment') { const blob = await attachment.content; captures.push({ file, size: blob.size, type: blob.type, references: context.parts.filter(part => part.kind === 'reference').map(part => part.reference) }); }
      return { status: 'added', partIds: context.parts.map(part => part.id) };
    } }
  };
  let controller: CadLiveController | null = null;
  const live = { bind(next: CadLiveController) { controller = next; return () => { controller = null; }; } };
  // One live binding per pane: whichever renderer the file selects binds the mounted view.
  const services = { client, preferences, commands, live };
  // `harness` is test scaffolding for the shell's own tools; it ships nowhere.
  const renderers = [createStepRenderer(services), createDxfRenderer(services), createGlbRenderer(services), createMeshRenderer(services), createRobotRenderer(services), createHarnessRenderer(services)];
  return { client, source, host, renderers, commands, capture, selectReference, get controller() { return controller; } };
}
const a = workspace('one'), b = workspace('two');
// Directory navigation hydrates before a renderer mounts. Large workspaces
// return path-only placeholders until the selected file is requested.
await Promise.all([a.client.refresh(), b.client.refresh()]);
function App() {
  // A file is normally REOPENED with what a previous session left for it: the open tab, the
  // display settings, the camera. `__cadViewerState` is how a test starts a page that way, so
  // "reopen this file" can be a real open against a stored state rather than a remount over a
  // live client that still holds everything it has already downloaded.
  const [state, setState] = useState<FileViewerState>(
    () => (window as unknown as { __cadViewerState?: FileViewerState }).__cadViewerState || { panel: '', panelWidth: 300 });
  const [otherState, setOtherState] = useState<FileViewerState>({ panel: '', panelWidth: 300 });
  const [second, setSecond] = useState(false);
  const [mounted, setMounted] = useState(true);
  const [fullscreen, setFullscreen] = useState(false);
  Object.assign(window, { cadHarness: { a, b, state, otherState, preferences, captures, opened, capture: a.capture, selectReference: a.selectReference, second: setSecond, mounted: setMounted, fullscreen: setFullscreen } });
  return <div style={{ display: 'flex', width: '1200px', height: '720px' }}>
    <section data-testid="one" style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column' }}>
      {mounted && <FileViewer fullscreen={fullscreen} onExitFullscreen={() => setFullscreen(false)} file={file} host={a.host} renderers={a.renderers} state={state} onStateChange={setState} />}
    </section>
    {second && <section data-testid="two" style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column' }}>
      <FileViewer file={file} host={b.host} renderers={b.renderers} state={otherState} onStateChange={setOtherState} />
    </section>}
  </div>;
}
createRoot(document.getElementById('root')!).render(<App />);
