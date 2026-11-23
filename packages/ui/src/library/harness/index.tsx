import { useState } from "react";
import { createRoot } from "react-dom/client";
import { FileViewer } from "../../file-viewer/index.js";
import { viewerLinks } from "../../file-viewer/navigation/links.js";
import { testHost } from "../../host/testing/host.js";
import { english } from "../../i18n/index.js";
import type { HomeLocation, NavigationTarget } from "../../host/types.js";
import { ModelLibrary, type LibraryModel, type LibraryProject } from "../ModelLibrary.js";

// The home under the viewer's navbar, as a host shows it, for the home's browser spec (`ModelLibrary.browser.test.mjs`)
// and for a look at the page: a few standalone documents and two projects, one of them with a folder that is gone.
// The page's address chooses what is on screen: `?place=pinned|standalone|<project id>` the place, `?from=<name>` the
// document just left, `?layout=list`, `?links=0` a host with no addresses, `?scheme=dark`, `?width=<px>` the home's
// width (the window's without it), `?panel=<json>` the sidebar as a host kept it (`{"open":false,"width":320}`). What
// the home asks its host to keep of the sidebar is on `window.homePanel`, as written, and the links it asked its host to
// open on `window.homeOpened`.
const params = new URLSearchParams(location.search);
const HOUR = 3600, NOW = Date.now() / 1000;
const ROOT = "/home/me/work/gearbox";
const row = (name: string, index: number, extra: Partial<LibraryModel> = {}): LibraryModel => ({ path: `/home/me/parts/${name}`, id: `id-${name}`, name,
  folder: "/home/me/parts", kind: "file", pinned: false, missing: false, opened: NOW - (index + 1) * HOUR, updated: NOW - (index + 3) * HOUR,
  created: NOW - 60 * HOUR, thumbnail: null, pictured: null, size: 4096 * (index + 1), ...extra });
const built = (name: string, index: number, script: string, extra: Partial<LibraryModel> = {}) => row(name, index, { path: `id-${name}`, kind: "model",
  script: `${ROOT}/${script}`, folder: `${ROOT}/src`, size: null, project: "gearbox", ...extra });
const PROJECTS: LibraryProject[] = [
  { id: "gearbox", name: "gearbox", root: ROOT, opened: NOW, missing: false, truncated: true, documents: [
    built("housing", 0, "src/housing.py", { pinned: true }), built("spur_gear", 1, "src/gears.py"),
    row("housing.step", 2, { path: `${ROOT}/exports/housing.step`, folder: `${ROOT}/exports`, project: "gearbox" }),
    ...Array.from({ length: 9 }, (_, index) => row(`plate_${index}.dxf`, index + 3, { path: `${ROOT}/dxf/plate_${index}.dxf`, folder: `${ROOT}/dxf`,
      opened: null, project: "gearbox" })),
  ] },
  { id: "lamp", name: "lamp", root: "/home/me/work/lamp", opened: NOW - 90 * HOUR, missing: true, documents: [] },
];
const RECENTS = [...PROJECTS[0].documents.slice(0, 3),
  ...["bracket.step", "hinge.step", "layered.dxf", "arm.urdf", "pair.glb"].map((name, index) => row(name, index + 3, { pinned: index === 0 }))];
const library = { list: async () => RECENTS, change: async () => RECENTS, thumbnail: async () => null, open: async () => {},
  projects: async () => PROJECTS, removeProject: async () => PROJECTS, pick: async () => {}, importFolder: async () => null };
// A host with addresses: a document's page by its id, a place's on the home.
const navigation = params.get("links") === "0" ? undefined : {
  hrefOf: (target: NavigationTarget) => "document" in target ? (target.document.startsWith("/") ? null : `/${target.document}`)
    : `/?place=${target.home.view === "project" ? target.home.project : target.home.view}`,
  openBeside: { kind: "tab" as const, open() {} },
};
const asked = params.get("place");
const start: HomeLocation = !asked || asked === "recents" ? { view: "recents" } : asked === "pinned" || asked === "standalone" ? { view: asked }
  : { view: "project", project: asked };
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
  return <ModelLibrary library={library} layout={layout} onLayoutChange={setLayout} sort={sort} onSortChange={setSort} home="/home/me"
    place={place} onPlaceChange={setPlace} navigation={navigation} from={from ? { path: `id-${from}`, id: `id-${from}`, name: from } : null} onBack={() => {}}
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
