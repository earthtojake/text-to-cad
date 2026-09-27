import { createRoot } from "react-dom/client";
import { createPortal } from "react-dom";
import { useEffect, useMemo, useState } from "react";
import { unavailablePromptContext } from "@hardcore/core/prompt";
import { FileText } from "lucide-react";
import { FileViewer, defineFileRenderer } from "../index.js";
import type { FileSource, FileActions, FileMetadata, FileRendererProps, FileViewerState, JsonValue, TextDocument } from "../types.js";

const events: string[] = [];
// Every file the viewer asked its host to open, with how: the host contract under test.
const opened: { path: string; options?: { target: "current" | "new"; panel?: string } }[] = [];
const rendererCallbacks = new Map<string, FileRendererProps<string>>();
const cleanupWrites = new Map<string, JsonValue>();
// How often each root's renderer rendered: FileViewer must not re-render it for its own chrome.
const renders: Record<string, number> = {};
function memorySource(id: string) {
  const files = new Map<string, TextDocument>([["notes.txt", { content: `${id} original`, revision: "1" }], ["next.txt", { content: `${id} next`, revision: "1" }], ["slow.txt", { content: `${id} slow`, revision: "1" }], ["readonly.txt", { content: "truncated", revision: "1", truncated: true }]]);
  const listeners = new Set<Parameters<NonNullable<FileSource["subscribe"]>>[0]>();
  const metadata = (path: string): FileMetadata => ({ path, name: path, kind: "file", extension: "txt", size: 20, mediaType: "text" });
  let failWrite = false;
  let holdWrites = false;
  let holdFirstListing = id === "root-a" && new URLSearchParams(window.location.search).has("initialList");
  const waitingWrites: (() => void)[] = [];
  const waitingTrash: (() => void)[] = [];
  const source: FileSource = {
    id, rootName: id,
    stat: async (path) => metadata(path),
    list: async (_directory, { signal }) => {
      events.push(`${id}:list`);
      if (holdFirstListing) {
        holdFirstListing = false;
        await new Promise<void>((_resolve, reject) => signal.addEventListener("abort", () => reject(signal.reason), { once: true }));
      }
      return [...files.keys()].map(metadata);
    },
    paths: async () => [...files.keys()],
    readText: async (path, { signal }) => {
      if (path === "slow.txt") await new Promise<void>((resolve, reject) => {
        const timer = setTimeout(resolve, 200);
        signal.addEventListener("abort", () => { clearTimeout(timer); events.push(`${id}:aborted`); reject(signal.reason); }, { once: true });
      });
      signal.throwIfAborted();
      return { ...files.get(path)! };
    },
    writeText: async (path, { content, expectedRevision }) => {
      if (holdWrites) await new Promise<void>((resolve) => waitingWrites.push(resolve));
      if (failWrite) return { status: "error", message: "disk is full" };
      const previous = files.get(path)!;
      if (expectedRevision !== previous.revision) return { status: "conflict" };
      const document = { content, revision: String(Number(previous.revision) + 1) };
      files.set(path, document);
      return { status: "saved", document };
    },
    subscribe(listener) { listeners.add(listener); events.push(`${id}:subscribe`); return () => { listeners.delete(listener); events.push(`${id}:unsubscribe`); }; },
    rename: async (path, { name }) => { const contents = files.get(path)!; files.delete(path); files.set(name, contents); return { status: "committed", path: name, change: { kind: "moved", from: path, to: name, entryKind: "file" } }; },
    create: async (_directory, { kind, name }) => { files.set(name, { content: "created", revision: "1" }); return { status: "committed", path: name, change: { kind: "added", path: name, entryKind: kind } }; },
    trash: async (path) => { await new Promise<void>(resolve => waitingTrash.push(resolve)); files.delete(path); return { status: "committed", path, change: { kind: "deleted", path, entryKind: "file" } }; },
  };
  const actions: FileActions = { perform: { "copy-relative-path": async (entry) => { events.push(`copy:${entry.path}`); } } };
  return { source, actions, files, change(path: string, content: string, notify = true) {
    const previous = files.get(path)!; files.set(path, { content, revision: String(Number(previous.revision) + 1) });
    if (notify) for (const listener of listeners) listener({ sourceId: id, changes: [{ kind: "content", path }] });
  }, fail(value: boolean) { failWrite = value; }, hold(value: boolean) { holdWrites = value; }, releaseWrites() { holdWrites = false; for (const release of waitingWrites.splice(0)) release(); }, releaseTrash() { for (const release of waitingTrash.splice(0)) release(); }, add(path: string) {
    files.set(path, { content: "added", revision: "1" });
    for (const listener of listeners) listener({ sourceId: id, changes: [{ kind: "content", path }] });
  } };
}
const a = memorySource("root-a"), b = memorySource("root-b");
function InMemoryRenderer(props: FileRendererProps<string>) {
  const { document, data, openPanel, panelSlot } = props;
  rendererCallbacks.set(props.source.id, props);
  renders[props.source.id] = (renders[props.source.id] ?? 0) + 1;
  useEffect(() => () => {
    const state = cleanupWrites.get(`${props.source.id}:${props.file.path}`);
    if (state) props.onStateChange(state);
  }, [props.source.id, props.file.path, props.onStateChange]);
  return <div>
    <div data-testid="payload">{data}</div>
    <textarea aria-label="Document" value={document?.value ?? ""} readOnly={document?.readOnly} onChange={(event) => document?.setValue(event.target.value)} />
    <button onClick={() => void document?.save()} disabled={document?.readOnly}>Save</button>
    <span data-testid="document-key">{document?.key}</span>
    {openPanel === "details" && panelSlot ? createPortal(<p>Injected panel</p>, panelSlot) : null}
  </div>;
}
const renderer = defineFileRenderer({
  id: "in-memory", priority: 100, matches: (file) => file.mediaType === "text",
  panels: () => [{ id: "details", label: "Details", icon: FileText, content: "slot" }],
  load: async () => ({ default: InMemoryRenderer }),
  prepare: async ({ file, source, signal }) => ({ data: `${source.id}:${file.path}`, text: await source.readText!(file.path, { signal }), dispose: () => { events.push(`${source.id}:${file.path}:disposed`); } }),
});
const renderers = [renderer];
const clipboard = { writeText: async () => {}, readText: async () => "", writeImage: async () => {} };
function host(root: ReturnType<typeof memorySource>, openFile: (path: string, options?: { target: "current" | "new"; panel?: string }) => void) { return { files: root.source, fileActions: root.actions, clipboard, promptContext: unavailablePromptContext, environment: { colorScheme: "light" as const }, navigation: { openFile } }; }
function App() {
  const [file, setFile] = useState("notes.txt");
  const [root, setRoot] = useState(a);
  const [second, setSecond] = useState(false);
  const [navigationPath, setNavigationPath] = useState<string | null | undefined>(undefined);
  const [state, setState] = useState<FileViewerState>({ panel: null, panelWidth: 300, expandedDirectories: [""] });
  const [otherState, setOtherState] = useState<FileViewerState>({ panel: "", panelWidth: 300 });
  Object.assign(window, { harness: { a, b, events, opened, rendererCallbacks, renders, cleanupWrites, state, open: setFile, navigationPath: setNavigationPath, setRoot: (id: string) => { setRoot(id === "root-b" ? b : a); }, second: setSecond, width: (panelWidth: number) => setState((previous) => ({ ...previous, panelWidth })) } });
  // A host is made once for its root, as an app makes it (FileViewer's props are compared by identity).
  const primaryHost = useMemo(() => host(root, (path, options) => { opened.push({ path, options }); setFile(path); setState((previous) => ({ ...previous, panel: options?.panel ?? null })); }), [root]);
  return <div style={{ width: "1000px", height: "650px" }}>
    <section data-testid="primary" style={{ height: "400px", display: "flex", flexDirection: "column" }}>
      {/* A host that shows one file at a time: an open moves this view to the file, with the panel it was opened with, or the file's own default. */}
      <FileViewer file={file} host={primaryHost} renderers={renderers} state={state} onStateChange={setState} navigationPath={navigationPath} />
    </section>
    {second ? <section data-testid="secondary" style={{ height: "240px" }}><FileViewer file="notes.txt" host={host(b, () => {})} renderers={renderers} state={otherState} onStateChange={setOtherState} /></section> : null}
  </div>;
}
createRoot(document.getElementById("root")!).render(<App />);
