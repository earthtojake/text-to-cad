import { createRoot } from 'react-dom/client';
import { useState } from 'react';
import { FileViewer } from '@text-to-cad/ui/file-viewer';
import type { FileSource } from '@text-to-cad/ui/file-viewer';
import { createCadClient } from '@text-to-cad/core/client';
import { createTabStore, memoryTabRecord, useTabViewerState } from '@text-to-cad/ui/tab-store';
import type { TabRecordStorage, TabStore } from '@text-to-cad/ui/tab-store';
import { createStepRenderer } from '@text-to-cad/ui/renderers/step';
import { createDxfRenderer } from '@text-to-cad/ui/renderers/dxf';
import { createGlbRenderer } from '@text-to-cad/ui/renderers/glb';
import { createMeshRenderer } from '@text-to-cad/ui/renderers/mesh';
import { createRobotRenderer } from '@text-to-cad/ui/renderers/robot';
import { createHarnessRenderer } from '@text-to-cad/ui/renderers/shell-harness';
import type { ViewerHost } from '@text-to-cad/ui/host';
import type { CadLiveController } from '@text-to-cad/ui/renderers/step';
import type { ViewerCommands as CadCommands } from '@text-to-cad/ui/renderers/workspace';

// The one file both panes open: `?file=arm.urdf` for a test whose fixture is not the default mesh.
const file = new URLSearchParams(location.search).get('file') || 'part.stl';
const captures: { file: string; size: number; type: string; references: unknown }[] = [];
// What a renderer asked the host to open (a mesh a robot description names, say).
const opened: string[] = [];
// The tab store, as a host builds it: over memory by default (a test seeds it through
// `window.__cadTabRecord`, so "reopen this file" is a real open against a stored record), or over
// this page's sessionStorage (`?store=session`), so a reload of the page is a reload of the tab
// and a new page is a new tab. Nothing under `renderers/` touches either.
const KEY = 'text-to-cad:tab:harness';
const sessionRecord = (): TabRecordStorage => ({
  read: () => JSON.parse(sessionStorage.getItem(KEY) || 'null'),
  write: record => sessionStorage.setItem(KEY, JSON.stringify(record)),
});
const tabStore = createTabStore(new URLSearchParams(location.search).get('store') === 'session'
  ? sessionRecord() : memoryTabRecord((window as unknown as { __cadTabRecord?: unknown }).__cadTabRecord));
const preferences = tabStore.settings;
// The second pane is another viewer, and so another tab: a tab keeps the view of the one file it
// shows (`TAB_FILE_LIMIT`), so two viewers sharing one record would drop each other's.
const otherTabStore = createTabStore(memoryTabRecord());
// The keyboard the browser under test types on, as a web host reports it: the drawing
// editor's history keys must be the ones its SDK listens for on this machine.
const keyboardPlatform = /Mac|iPhone|iPad/.test(navigator.platform) ? 'darwin' : /Win/.test(navigator.platform) ? 'win32' : 'linux';
function workspace(id: string, store: TabStore) {
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
  // A test that gives the root an absolute home (`window.__cadReferenceRoot`) gets a host that names
  // files by it in copied references, as one whose root is a whole filesystem does.
  const referenceRoot = (window as unknown as { __cadReferenceRoot?: string }).__cadReferenceRoot;
  const source: FileSource = {
    id, rootName: id,
    ...(referenceRoot ? { referencePath: (path: string) => `${referenceRoot}/${path}` } : {}),
    stat: async (path) => ({ path, name: path, kind: 'file', size: 400, extension: path.split('.').pop() || '' }),
    list: async () => [{ path: file, name: file, kind: 'file' }]
  };
  const destination = { kind: (window as unknown as { __cadPromptDestination?: 'clipboard' }).__cadPromptDestination || 'composer' as const, available: true };
  const host: ViewerHost = { files: source, navigation: { openFile(path) { opened.push(path); } }, environment: { colorScheme: 'dark', platform: keyboardPlatform },
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
  const services = { client, preferences: store.settings, commands, live };
  // `harness` is test scaffolding for the shell's own tools; it ships nowhere.
  const renderers = [createStepRenderer(services), createDxfRenderer(services), createGlbRenderer(services), createMeshRenderer(services), createRobotRenderer(services), createHarnessRenderer(services)];
  return { client, source, host, renderers, commands, capture, selectReference, get controller() { return controller; } };
}
const a = workspace('one', tabStore), b = workspace('two', otherTabStore);
// Directory navigation hydrates before a renderer mounts. Large workspaces
// return path-only placeholders until the selected file is requested.
await Promise.all([a.client.refresh(), b.client.refresh()]);
function App() {
  // Two panes, two roots, two tabs: each viewer keeps its own record, settings and file view.
  const { state, onStateChange } = useTabViewerState(tabStore, a.source.id);
  const { state: otherState, onStateChange: onOtherStateChange } = useTabViewerState(otherTabStore, b.source.id);
  const [second, setSecond] = useState(false);
  const [mounted, setMounted] = useState(true);
  Object.assign(window, { cadHarness: { a, b, state, otherState, preferences, tabStore, record: tabStore.getSnapshot(), captures, opened, capture: a.capture, selectReference: a.selectReference, second: setSecond, mounted: setMounted } });
  return <div style={{ display: 'flex', width: '1200px', height: '720px' }}>
    <section data-testid="one" style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column' }}>
      {mounted && <FileViewer file={file} host={a.host} renderers={a.renderers} state={state} onStateChange={onStateChange} />}
    </section>
    {second && <section data-testid="two" style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column' }}>
      <FileViewer file={file} host={b.host} renderers={b.renderers} state={otherState} onStateChange={onOtherStateChange} />
    </section>}
  </div>;
}
createRoot(document.getElementById('root')!).render(<App />);
