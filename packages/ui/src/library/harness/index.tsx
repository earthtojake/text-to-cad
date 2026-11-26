import { useState } from "react";
import { createRoot } from "react-dom/client";
import { FileViewer } from "../../file-viewer/index.js";
import { viewerLinks } from "../../file-viewer/navigation/links.js";
import { testHost } from "../../host/testing/host.js";
import { english } from "../../i18n/index.js";
import type { HomeLocation, NavigationTarget } from "../../host/types.js";
import { ModelLibrary, type LibraryFolder, type LibraryModel, type LibraryProject } from "../ModelLibrary.js";

// The home under the viewer's navbar, as a host shows it, for the home's browser spec (`ModelLibrary.browser.test.mjs`)
// and for a look at the page: a few documents in no project and three projects: gearbox, a tree of folders; an empty one;
// and one whose folder is gone. A project's folder is answered as a CAD host answers it (`GET /api/v1/projects/<id>`):
// its subfolders that hold a file somewhere below, then its files; with words, every file below it that holds them all. gearbox holds an engineer's other files too (a datasheet, a script,
// notes, another tool's native file, a file of an unknown kind and one with no extension): files the viewer does not open,
// listed with the rest and opened in the computer's apps (`fileActions`: Open in's apps as a CAD host answers them).
// The page's address chooses what is on screen: `?place=pinned|<project id>` the place (Starred, or a project; `&path=` a folder
// of a project), `?from=<name>` the document just left, `?layout=list`, `?links=0` a host with no addresses,
// `?scheme=dark`, `?width=<px>` the home's width (the window's without it), `?panel=<json>` the sidebar as a host kept
// it (`{"open":false,"width":320}`), `?state=empty` a library with nothing in it yet (the welcome), `?state=reading` one
// whose list never answers (the placeholders), `?state=failing` one whose documents do not open (the error's line),
// `?state=partial` a host that lists only part of each folder, `?actions=0` a host that can do nothing with a file.
// What the home asked its host to open in an app is on `window.homeOpenedIn`. What the home asks its host to keep of the sidebar is on `window.homePanel`, as
// written, the links it asked its host to open on `window.homeOpened`, and the folders it asked for on
// `window.homeFolders`.
const params = new URLSearchParams(location.search);
const state = params.get("state");
const HOUR = 3600, NOW = Date.now() / 1000;
const ROOT = "/home/me/work/gearbox";
const KINDS: Record<string, string> = { xbf: "model", step: "step", dxf: "dxf", stl: "stl", glb: "glb", urdf: "urdf" };
const row = (path: string, index: number, extra: Partial<LibraryModel> = {}): LibraryModel => {
  const name = path.split("/").pop()!;
  return { path, id: `id-${name}`, name, folder: path.slice(0, path.lastIndexOf("/")), documentKind: KINDS[name.split(".").pop()!] ?? null,
    pinned: false, missing: false, opened: NOW - (index + 1) * HOUR, updated: NOW - (index + 3) * HOUR, created: NOW - 60 * HOUR,
    thumbnail: null, pictured: null, size: 4096 * (index + 1), project: path.startsWith(`${ROOT}/`) ? "gearbox" : null, ...extra };
};
// gearbox's files, by their path below its root; a file no page opened has no opened or created time.
const TREE: LibraryModel[] = [
  row(`${ROOT}/gearbox.xbf`, 0, { parts: 14 }), row(`${ROOT}/spur_gear.xbf`, 1, { parts: 1 }),
  row(`${ROOT}/housing/v3/housing.xbf`, 2, { pinned: true, parts: 3 }), row(`${ROOT}/housing/v3/lid.step`, 3, { opened: null, created: null }),
  row(`${ROOT}/housing/v3/drawings/housing-plan.dxf`, 4, { opened: null, created: null }),
  row(`${ROOT}/housing/v2/housing.xbf`, 5, { opened: null, created: null }),
  row(`${ROOT}/exports/housing.step`, 6),
  ...Array.from({ length: 9 }, (_, index) => row(`${ROOT}/dxf/plate_${index}.dxf`, index + 7, { opened: null, created: null })),
];
// The files of gearbox the viewer does not open, as a CAD host lists them: no document kind, no picture, never opened.
const other = (path: string, index: number) => row(path, index, { opened: null, created: null });
TREE.push(other(`${ROOT}/bearing-6204-datasheet.pdf`, 21), other(`${ROOT}/build.py`, 22), other(`${ROOT}/NOTES.md`, 23),
  other(`${ROOT}/gearbox.f3d`, 24), other(`${ROOT}/tolerances.dat`, 25), other(`${ROOT}/Makefile`, 26), other(`${ROOT}/housing/v3/run.sh`, 27));
// Open in's apps for a file that is no document: one target, the file itself; none and no default handler for a program.
const APPS: Record<string, { id: string; name: string }[]> = { pdf: [{ id: "okular", name: "Okular" }], py: [{ id: "vscode", name: "VS Code" }, { id: "pycharm", name: "PyCharm" }],
  md: [{ id: "vscode", name: "VS Code" }], f3d: [], xbf: [{ id: "vscode", name: "VS Code" }], step: [{ id: "freecad", name: "FreeCAD" }] };
// The files the OS's own handler is never started on: a script (a model's too), and anything that could be a program.
const NO_DEFAULT = new Set(["py", "sh", "xbf"]);
const fileActions = params.get("actions") === "0" ? undefined : {
  platform: "linux" as const,
  perform: { "copy-path": () => {}, reveal: () => {}, "copy-link": () => {} },
  apps: async (entry: { path: string }) => {
    const name = entry.path.split("/").pop()!, extension = name.includes(".") ? name.split(".").pop()! : "";
    return { targets: [{ target: "source", kind: "file", name, present: true, apps: APPS[extension] ?? [], ...(NO_DEFAULT.has(extension) ? { default: false } : null) }], fileManager: "file manager" };
  },
  openApp: (entry: { path: string }, target: string, app: string) => { const page = window as unknown as { homeOpenedIn?: unknown[] }; (page.homeOpenedIn ??= []).push({ path: entry.path, target, app }); },
};
// Folders whose names are long, for a look at a deep path in the heading.
TREE.push(row(`${ROOT}/housing/v3/drawings/assembly instructions for the second production batch/step 01 exploded view.dxf`, 20, { opened: null, created: null }));
const PROJECTS: LibraryProject[] = [
  { id: "gearbox", name: "gearbox", root: ROOT, opened: NOW, missing: false },
  { id: "bare", name: "bare", root: "/home/me/work/bare", opened: NOW - 30 * HOUR, missing: false },
  { id: "lamp", name: "lamp", root: "/home/me/work/lamp", opened: NOW - 90 * HOUR, missing: true },
];
const asked: unknown[] = ((window as unknown as { homeFolders?: unknown[] }).homeFolders = []);
const collator = new Intl.Collator("en", { numeric: true });
async function folder(project: string, { path = "", q = "" }: { path?: string; q?: string }): Promise<LibraryFolder> {
  asked.push({ project, path, q });
  const found = PROJECTS.find(entry => entry.id === project);
  if (!found) throw new Error(`no project ${project}`);
  const files = project === "gearbox" ? TREE : [];
  const base = path ? `${found.root}/${path}` : found.root;
  if (path && !files.some(file => file.path.startsWith(`${base}/`))) throw new Error(`no folder ${path} in ${found.name}`);
  const below = files.filter(file => file.path.startsWith(`${base}/`)).map(file => ({ file, rest: file.path.slice(base.length + 1) }));
  const words = q.trim().toLowerCase().split(/\s+/).filter(Boolean);
  if (words.length) {
    const documents = below.filter(({ rest }) => words.every(word => rest.toLowerCase().includes(word))).map(({ file }) => file);
    return { project: found, path, folders: [], documents, truncated: false };
  }
  const names = [...new Set(below.filter(({ rest }) => rest.includes("/")).map(({ rest }) => rest.split("/")[0]))].sort(collator.compare);
  return { project: found, path, folders: names.map(name => ({ name, path: path ? `${path}/${name}` : name })),
    documents: below.filter(({ rest }) => !rest.includes("/")).map(({ file }) => file).sort((a, b) => collator.compare(a.name, b.name)), truncated: state === "partial" };
}
const RECENTS = [TREE[2], TREE[0], TREE[6], ...["bracket.step", "hinge.step", "layered.dxf", "arm.urdf", "pair.glb"]
  .map((name, index) => row(`/home/me/parts/${name}`, index + 3, { pinned: index === 0 }))];
const never = new Promise<never>(() => {});
const library = { list: () => state === "reading" ? never : Promise.resolve(state === "empty" ? [] : RECENTS), change: async () => RECENTS, thumbnail: async () => null,
  open: async () => { if (state === "failing") throw new Error("The file could not be opened."); },
  projects: async () => state === "empty" ? [] : PROJECTS, folder, removeProject: async () => PROJECTS, pick: async () => {}, importFolder: async () => null };
// A host with addresses: a document's page by its id, a place's on the home.
const navigation = params.get("links") === "0" ? undefined : {
  hrefOf: (target: NavigationTarget) => "document" in target ? (target.document.startsWith("/") ? null : `/${target.document}`)
    : target.home.view === "project" ? `/?place=${target.home.project}${target.home.path ? `&path=${encodeURIComponent(target.home.path)}` : ""}`
      : `/?place=${target.home.view}`,
  openBeside: { kind: "tab" as const, open() {} },
};
const named = params.get("place");
const start: HomeLocation = !named || named === "recents" ? { view: "recents" } : named === "pinned" ? { view: named }
  : { view: "project", project: named, ...(params.get("path") ? { path: params.get("path")! } : {}) };
const scheme = params.get("scheme") === "dark" ? "dark" as const : "light" as const;
// The way home (the navbar's logo): Recents, shown in place; a link where the host has addresses.
let showPlace: (place: HomeLocation) => void = () => {};
const host = testHost({ navigation: { openFile() {}, home: () => showPlace({ view: "recents" }), ...(navigation ? { hrefOf: navigation.hrefOf } : null) },
  environment: { colorScheme: scheme, platform: "linux" },
  // Its links, followed the host's way: what was opened is on `window.homeOpened`, and the page goes nowhere.
  links: viewerLinks({ version: "0.7.4", github: "https://github.com/example/cad", discord: "https://discord.gg/example",
    open: async url => { const page = window as unknown as { homeOpened?: string[] }; (page.homeOpened ??= []).push(url); } }) });
const keptPanel = (() => { try { return JSON.parse(params.get("panel") ?? "null") as object | null; } catch { return null; } })();

function Home() {
  const [place, setPlace] = useState(start);
  const [layout, setLayout] = useState<"grid" | "list">(params.get("layout") === "list" ? "list" : "grid");
  const [sort, setSort] = useState<"activity" | "name" | "kind">("activity");
  const from = params.get("from");
  showPlace = setPlace;
  return <ModelLibrary library={library} fileActions={fileActions} layout={layout} onLayoutChange={setLayout} sort={sort} onSortChange={setSort}
    place={place} onPlaceChange={setPlace} navigation={navigation} from={from ? { path: `/elsewhere/${from}`, id: `id-${from}`, name: from } : null} onBack={() => {}}
    panel={keptPanel} onPanelChange={panel => { (window as unknown as { homePanel?: object }).homePanel = panel; }} />;
}

// The person's settings, as a host hands them to the app's menu (Settings' cog, in the sidebar's foot).
function Page() {
  const [theme, setTheme] = useState<"system" | "light" | "dark">("system");
  const [telemetry, setTelemetry] = useState(false);
  return <FileViewer file={null} host={host} renderers={[]} state={{}} onStateChange={() => {}} presentation={{ home: <Home /> }}
    colorScheme={{ preference: theme, onPreferenceChange: setTheme }}
    appSettings={[{ id: "analytics", label: english("consent.shareUsage"), checked: telemetry, onCheckedChange: setTelemetry }]} />;
}

const width = Number(params.get("width")) || 0;
createRoot(document.getElementById("root")!).render(<div className={scheme === "dark" ? "dark" : undefined} data-testid="home"
  style={{ display: "flex", flexDirection: "column", width: width ? `${width}px` : "100vw", height: "100vh" }}>
  <Page />
</div>);
