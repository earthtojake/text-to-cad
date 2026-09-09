import { createRoot } from "react-dom/client";
import { createPortal } from "react-dom";
import { useEffect, useState } from "react";
import { FileText } from "lucide-react";
import { FileViewer, defineFileRenderer } from "../index.js";
import type { FileSource, FileMetadata, FileRendererProps, FileViewerState, JsonValue, TextDocument } from "../types.js";

const events: string[] = [];
const rendererCallbacks = new Map<string, FileRendererProps<string>>();
const cleanupWrites = new Map<string, JsonValue>();
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
    actions: {
      rename: async (entry, name) => { const contents = files.get(entry.path)!; files.delete(entry.path); files.set(name, contents); return name; },
      create: async (_directory, _kind, name) => { files.set(name, { content: "created", revision: "1" }); return name; },
      trash: async () => { await new Promise<void>(resolve => waitingTrash.push(resolve)); return true; },
      perform: { "copy-relative-path": async (entry) => { events.push(`copy:${entry.path}`); } },
    },
  };
  return { source, files, change(path: string, content: string, notify = true) {
    const previous = files.get(path)!; files.set(path, { content, revision: String(Number(previous.revision) + 1) });
    if (notify) for (const listener of listeners) listener({ sourceId: id, paths: [path] });
  }, fail(value: boolean) { failWrite = value; }, hold(value: boolean) { holdWrites = value; }, releaseWrites() { holdWrites = false; for (const release of waitingWrites.splice(0)) release(); }, releaseTrash() { for (const release of waitingTrash.splice(0)) release(); }, add(path: string) {
    files.set(path, { content: "added", revision: "1" });
    for (const listener of listeners) listener({ sourceId: id, paths: [path] });
  } };
}
const a = memorySource("root-a"), b = memorySource("root-b");
function InMemoryRenderer(props: FileRendererProps<string>) {
  const { document, data, openPanel, panelSlot, onChromeVisibilityChange } = props;
  rendererCallbacks.set(props.source.id, props);
  useEffect(() => () => {
    const state = cleanupWrites.get(`${props.source.id}:${props.file.path}`);
    if (state) props.onStateChange(state);
  }, [props.source.id, props.file.path, props.onStateChange]);
  return <div>
    <div data-testid="payload">{data}</div>
    <textarea aria-label="Document" value={document?.value ?? ""} readOnly={document?.readOnly} onChange={(event) => document?.setValue(event.target.value)} />
    <button onClick={() => void document?.save()} disabled={document?.readOnly}>Save</button>
    <button onClick={() => onChromeVisibilityChange(false)}>Preview</button>
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
function App() {
  const [file, setFile] = useState("notes.txt");
  const [root, setRoot] = useState(a);
  const [second, setSecond] = useState(false);
  const [narrowCrumbs, setNarrowCrumbs] = useState<boolean | undefined>(undefined);
  const [navigationPath, setNavigationPath] = useState<string | null | undefined>(undefined);
  const [state, setState] = useState<FileViewerState>({ panel: null, panelWidth: 300, expandedDirectories: [""] });
  const [otherState, setOtherState] = useState<FileViewerState>({ panel: "", panelWidth: 300 });
  Object.assign(window, { harness: { a, b, events, rendererCallbacks, cleanupWrites, state, open: setFile, narrowCrumbs: setNarrowCrumbs, navigationPath: setNavigationPath, setRoot: (id: string) => { setRoot(id === "root-b" ? b : a); }, second: setSecond, width: (panelWidth: number) => setState((previous) => ({ ...previous, panelWidth })) } });
  return <div style={{ width: "1000px", height: "650px" }}>
    <section data-testid="primary" style={{ height: "400px", display: "flex", flexDirection: "column" }}>
      <FileViewer file={file} source={root.source} renderers={renderers} state={state} onStateChange={setState} narrowCrumbs={narrowCrumbs} navigationPath={navigationPath}
        presentation={{ activity: value => value?.loading ? <span data-testid="activity">{value.title || value.label}</span> : null }}
        onOpenFile={(path) => { setFile(path); setState((previous) => ({ ...previous, panel: null })); }} />
    </section>
    {second ? <section data-testid="secondary" style={{ height: "240px" }}><FileViewer file="notes.txt" source={b.source} renderers={renderers} state={otherState} onStateChange={setOtherState} onOpenFile={() => {}} /></section> : null}
  </div>;
}
createRoot(document.getElementById("root")!).render(<App />);
