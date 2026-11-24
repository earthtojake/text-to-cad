import { createRoot } from 'react-dom/client';
import { useState } from 'react';
import { FileViewer } from '@cad/ui/file-viewer';
import type { FileSource } from '@cad/ui/file-viewer';
import { createCadClient, createHttpPromptFiles } from '@cad/core/client';
import { createTabStore, memoryTabRecord, useTabViewerState } from '@cad/ui/tab-store';
import type { TabRecordStorage, TabStore } from '@cad/ui/tab-store';
import { createBoardRenderer } from '@cad/ui/renderers/board';
import { createSchematicRenderer } from '@cad/ui/renderers/schematic';
import { createDxfRenderer } from '@cad/ui/renderers/dxf';
import { createGlbRenderer } from '@cad/ui/renderers/glb';
import { createMeshRenderer } from '@cad/ui/renderers/mesh';
import { createRobotRenderer } from '@cad/ui/renderers/robot';
import { createXbfRenderer } from '@cad/ui/renderers/xbf';
import { createHarnessRenderer } from '@cad/ui/renderers/shell-harness';
import type { ViewerHost } from '@cad/ui/host';
import type { LiveViewController } from '@cad/ui/renderers/xbf';
import type { ViewerCommands as CadCommands } from '@cad/ui/renderers/workspace';
// The module the built renderers publish their export view through (the viewer's ExportControls
// provides it): the same built file, so this harness's provider is the one they reach.
import { ExportContext } from '../../../dist/export/context.js';
import { ModelLibrary } from '@cad/ui/library';
// `?file=home`: no file, the host's home (the library), as the web viewer's is, for a look at the home page.
const showHome = new URLSearchParams(location.search).get('file') === 'home';
const HOME_MODELS = ['bracket.step', 'hinge.step', 'blinky.kicad_pcb', 'layered.dxf', 'arm.urdf', 'pair.glb'].map((name, index) => ({
  path: `/models/${name}`, name, kind: 'file', pinned: index === 0, modified: Date.now() - index * 3600e3, size: 4096 * (index + 1) }));
const homeLibrary = { list: async () => HOME_MODELS, change: async () => HOME_MODELS, thumbnail: async () => null, open: async () => {} };
const homePresentation = showHome ? { home: <ModelLibrary library={homeLibrary as never} onLayoutChange={() => {}} /> } : undefined;

// The one file both panes open, by its absolute path, as a viewer names files: a fixture server
// lists each of its files under `/models`, so `?file=arm.urdf` (for a test whose fixture is not the
// default mesh) is `/models/arm.urdf`.
const requested = new URLSearchParams(location.search).get('file') || 'part.stl';
const file = requested.startsWith('/') ? requested : `/models/${requested}`;
// The host's theme: dark, as the viewer opens, unless `?scheme=light` asks for the light one.
const colorScheme = new URLSearchParams(location.search).get('scheme') === 'light' ? 'light' as const : 'dark' as const;
// The language the panes read in (`?locale=ja`): English unless asked.
const locale = new URLSearchParams(location.search).get('locale') || undefined;
const promptMessages: string[] = [];
const captures: { file: string; size: number; type: string; references: unknown }[] = [];
// What a renderer asked the host to open (a mesh a robot description names, say).
const opened: string[] = [];
// What the first pane's renderer handed Export, in order: what a host's Export menu would offer.
const exportViews: unknown[] = [];
const publishExportView = (view: unknown) => { exportViews.push(view); };
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
// The viewport's Background: the scenarios were written for a picture in the host's theme, so the harness starts it
// as the host's colour scheme (`colorScheme`: Dark on a dark host) unless `?background=light|dark` asks for one, or a stored record
// already names one.
{
  const asked = new URLSearchParams(location.search).get('background');
  const stored = (window as unknown as { __cadTabRecord?: { settings?: { viewportBackground?: string } } }).__cadTabRecord?.settings?.viewportBackground;
  if (asked === 'light' || asked === 'dark') preferences.update({ viewportBackground: asked });
  else if (!stored) preferences.update({ viewportBackground: colorScheme });
}
// A scenario changes it as Display's Background does: the tab's setting, every view of the tab.
(window as unknown as { __cadViewportBackground?: (next: 'light' | 'dark') => void }).__cadViewportBackground =
  next => preferences.update({ viewportBackground: next });
// The second pane is another viewer, and so another tab: a tab keeps the view of the one file it
// shows (`TAB_FILE_LIMIT`), so two viewers sharing one record would drop each other's.
const otherTabStore = createTabStore(memoryTabRecord());
otherTabStore.settings.update({ viewportBackground: tabStore.settings.getSnapshot().viewportBackground });
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
  const client = createCadClient({ origin: `${location.origin}/${id}`, pollIntervalMs: 0 });
  // The pane's files: the one it shows, which is also all its explorer lists and finds.
  const name = file.split('/').pop() || file;
  const source: FileSource = {
    id,
    // A spec may hold the file's stat back (`window.__cadHoldStat`, a promise): the page's own phase, before any view is up.
    stat: async (path) => {
      await (window as unknown as { __cadHoldStat?: Promise<void> }).__cadHoldStat;
      return { path, name: path.split('/').pop() || path, kind: 'file', size: 400, extension: path.split('.').pop() || '' };
    },
    list: async () => [{ path: file, name, kind: 'file' }],
    search: async () => ({ paths: [file], truncated: false })
  };
  const destination = { kind: (window as unknown as { __cadPromptDestination?: 'clipboard' }).__cadPromptDestination || 'composer' as const, available: true };
  // `?home=1`: a host with a home and the file's ⋯ (Copy path), as the web viewer is, so the navbar's left end is whole.
  const homed = new URLSearchParams(location.search).get('home') === '1';
  const host: ViewerHost = { files: source, navigation: { openFile(path) { opened.push(path); }, ...(homed ? { home() {} } : null) },
    ...(homed ? { fileActions: { platform: keyboardPlatform, perform: { 'copy-path': async () => {} } } } : null), environment: { colorScheme, platform: keyboardPlatform, locale },
    clipboard: { writeText: async text => { promptMessages.push(await text); }, writeImage: async () => {} },
    promptFiles: createHttpPromptFiles({ origin: `${location.origin}/${id}` }),
    promptContext: { getSnapshot: () => destination, subscribe: () => () => {}, deliver: async context => {
      const attachment = context.parts.find(part => part.kind === 'attachment');
      if (attachment?.kind === 'attachment') { const blob = await attachment.content; captures.push({ file, size: blob.size, type: blob.type, references: context.parts.filter(part => part.kind === 'reference').map(part => part.reference) }); }
      return { status: 'added', partIds: context.parts.map(part => part.id) };
    } }
  };
  let controller: LiveViewController | null = null;
  const live = { bind(next: LiveViewController) { controller = next; return () => { controller = null; }; } };
  // One live binding per pane: whichever renderer the file selects binds the mounted view.
  const services = { client, preferences: store.settings, commands, live };
  // `harness` is test scaffolding for the shell's own tools; it ships nowhere.
  const renderers = [createBoardRenderer(services), createSchematicRenderer(services), createDxfRenderer(services), createGlbRenderer(services), createMeshRenderer(services), createRobotRenderer(services), createXbfRenderer(services), createHarnessRenderer(services)];
  return { client, source, host, renderers, commands, capture, selectReference, get controller() { return controller; } };
}
const a = workspace('one', tabStore), b = workspace('two', otherTabStore);
// Each client's catalog is read before a renderer mounts, as a host's first read of it is.
await Promise.all([a.client.refresh(), b.client.refresh()]);
function App() {
  // Two panes, two viewers, two tabs: each viewer keeps its own record, settings and file view.
  const { state, onStateChange } = useTabViewerState(tabStore);
  const { state: otherState, onStateChange: onOtherStateChange } = useTabViewerState(otherTabStore);
  const [second, setSecond] = useState(false);
  const [mounted, setMounted] = useState(true);
  Object.assign(window, { cadHarness: { a, b, state, otherState, preferences, tabStore, record: tabStore.getSnapshot(), captures, promptMessages, opened, exportViews, capture: a.capture, selectReference: a.selectReference, second: setSecond, mounted: setMounted } });
  return <div className="dark" style={{ display: 'flex', width: '1200px', height: '720px' }}>
    <section data-testid="one" style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column' }}>
      {mounted && <ExportContext.Provider value={publishExportView}><FileViewer file={showHome ? null : file} host={a.host} renderers={a.renderers} state={state} onStateChange={onStateChange} presentation={homePresentation} /></ExportContext.Provider>}
    </section>
    {second && <section data-testid="two" style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column' }}>
      <FileViewer file={file} host={b.host} renderers={b.renderers} state={otherState} onStateChange={onOtherStateChange} />
    </section>}
  </div>;
}
createRoot(document.getElementById('root')!).render(<App />);
