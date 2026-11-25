import { useEffect, useMemo, useState } from "react";
import { unavailablePromptContext } from "@cad/core/prompt";
import { FileViewer, defineFileRenderer } from "../index.js";
import type { FileActions, FileMetadata, FileProject, FileRendererProps, FileSource, FileViewerState, JsonValue } from "../types.js";

const events: string[] = [];
// Every file the viewer asked its host to show: the host contract under test.
const opened: string[] = [];
const rendererCallbacks = new Map<string, FileRendererProps<string>>();
const cleanupWrites = new Map<string, JsonValue>();
// How often each source's renderer rendered: FileViewer must not re-render it for its own chrome.
const renders: Record<string, number> = {};
let mounts = 0;
const FOLDER = "/work";

/**
 * A disk of text files by absolute path, the same paths in every source and each source's own
 * words in them, so a write that lands in the wrong source shows. The source states, lists and
 * searches; the renderer reads a file's text as it prepares it (`read`).
 */
function memorySource(id: string) {
  const files = new Map<string, string>(["notes", "next", "slow"].map(name => [`${FOLDER}/${name}.txt`, `${id} ${name}`]));
  const metadata = (path: string): FileMetadata => ({ path, name: path.split("/").pop()!, kind: "file", extension: "txt", size: 20, mediaType: "text", revision: files.get(path) });
  const source: FileSource = {
    id,
    stat: async (path) => { if (!files.has(path)) throw new Error(`File does not exist: ${path}`); return metadata(path); },
  };
  const read = async (path: string, signal: AbortSignal) => {
    if (path.endsWith("/slow.txt")) await new Promise<void>((resolve, reject) => {
      const timer = setTimeout(resolve, 200);
      signal.addEventListener("abort", () => { clearTimeout(timer); events.push(`${id}:aborted`); reject(signal.reason); }, { once: true });
    });
    signal.throwIfAborted();
    return files.get(path)!;
  };
  const actions: FileActions = { perform: { "copy-path": async (entry) => { events.push(`copy:${entry.path}`); } } };
  return { source, actions, files, read };
}
const a = memorySource("root-a"), b = memorySource("root-b");
const sources = { "root-a": a, "root-b": b } as const;
function InMemoryRenderer(props: FileRendererProps<string>) {
  const { data } = props;
  const [mount] = useState(() => (mounts += 1));
  rendererCallbacks.set(props.source.id, props);
  renders[props.source.id] = (renders[props.source.id] ?? 0) + 1;
  useEffect(() => () => {
    const state = cleanupWrites.get(`${props.source.id}:${props.file.path}`);
    if (state) props.onStateChange(state);
  }, [props.source.id, props.file.path, props.onStateChange]);
  return <div>
    <output data-testid="payload">{data}</output>
    <span data-testid="mount">{mount}</span>
  </div>;
}
const renderer = defineFileRenderer({
  id: "in-memory", priority: 100, matches: (file) => file.mediaType === "text",
  load: async () => ({ default: InMemoryRenderer }),
  prepare: async ({ file, source, signal }) => ({ data: await sources[source.id as keyof typeof sources].read(file.path, signal),
    dispose: () => { events.push(`${source.id}:${file.path}:disposed`); } }),
});
const renderers = [renderer];
const clipboard = { writeText: async () => {}, writeImage: async () => {} };
function host(root: ReturnType<typeof memorySource>, openFile: (path: string) => void) {
  return { files: root.source, fileActions: root.actions, clipboard, promptContext: unavailablePromptContext, environment: { colorScheme: "light" as const }, navigation: { openFile } };
}
/** The page both the browser spec and the jsdom tests drive: one host, a second on request; `window.harness` is its handle. */
export function App() {
  const [file, setFile] = useState<string | null>(`${FOLDER}/notes.txt`);
  const [root, setRoot] = useState(a);
  const [second, setSecond] = useState(false);
  const [state, setState] = useState<FileViewerState>({});
  const [otherState, setOtherState] = useState<FileViewerState>({});
  // A viewer that is not the page's own, drawn out of sight at 480 × 360, its layout pinned (`"pinned"`), or none.
  const [picture, setPicture] = useState<"none" | "pinned">("none");
  const [pictureState, setPictureState] = useState<FileViewerState>({});
  // The project the file on screen is in, where a spec names one: its name before the file's in the navbar.
  const [project, setProject] = useState<FileProject | null>(null);
  const showProject = (named: Omit<FileProject, "onShow"> | null) =>
    setProject(named ? { ...named, onShow: () => { events.push(`project:${named.id}`); } } : null);
  Object.assign(window, { harness: { a, b, events, opened, rendererCallbacks, renders, cleanupWrites, state, open: setFile,
    setRoot: (id: string) => { setRoot(id === "root-b" ? b : a); }, second: setSecond, picture: setPicture, project: showProject } });
  // A host is made once for its source, as an app makes it (FileViewer's props are compared by identity).
  const primaryHost = useMemo(() => host(root, (path) => { opened.push(path); setFile(path); }), [root]);
  return <div style={{ width: "1000px", height: "650px" }}>
    <section data-testid="primary" style={{ height: "400px", display: "flex", flexDirection: "column" }}>
      {/* A host that shows one file at a time: a pick moves this view to the file. */}
      <FileViewer file={file} host={primaryHost} renderers={renderers} state={state} onStateChange={setState} project={project} />
    </section>
    {second ? <section data-testid="secondary" style={{ height: "240px" }}><FileViewer file={`${FOLDER}/notes.txt`} host={host(b, () => {})} renderers={renderers} state={otherState} onStateChange={setOtherState} /></section> : null}
    {picture === "none" ? null : <div aria-hidden="true" data-testid="picture"
      style={{ position: "fixed", left: 0, top: 0, width: 480, height: 360, opacity: 0, pointerEvents: "none", zIndex: -1, overflow: "hidden" }}>
      <FileViewer file={`${FOLDER}/notes.txt`} host={host(b, () => {})} renderers={renderers} state={pictureState} onStateChange={setPictureState}
        layout="mobile" />
    </div>}
  </div>;
}
