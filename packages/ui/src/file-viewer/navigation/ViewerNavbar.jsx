import { ArrowLeft, ArrowRight, ChevronDown, Ellipsis } from "lucide-react";
import { Fragment, useEffect, useRef, useState } from "react";

import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuSub, DropdownMenuSubContent, DropdownMenuSubTrigger, DropdownMenuTrigger } from "@text-to-cad/ui/primitives/dropdown-menu";
import { Popover, PopoverContent, PopoverTrigger } from "@text-to-cad/ui/primitives/popover";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@text-to-cad/ui/primitives/tabs";
import { TooltipHint } from "@text-to-cad/ui/primitives/tooltip";
import { useI18n } from "@text-to-cad/ui/i18n";
import { cn } from "@text-to-cad/ui/utils";

import logo from "../../assets/logo-c.svg";
import { NAVBAR_CONTROLS_CLASS, NAVBAR_ROW_CLASS } from "../../lib/navbarRow.js";
import { FLOATING_SURFACE_CLASS } from "../../lib/floatingSurface.js";
import { useViewerMobile } from "../responsive.js";

import { AppMenu } from "./AppMenu.jsx";
import { openInMenu } from "./entry-menu.js";
import { FolderExplorer } from "./FolderExplorer.jsx";
import { ModelList } from "./ModelList.jsx";
import { useControlUsage } from "../../usage/controls.js";

// The file menu's items as telemetry names them (`usage/controls.js`): an app chosen in Open in is
// `file_open_app`, never which app; Open in's Browser is counted by none.
const FILE_ACTION_CONTROLS = Object.freeze({ "copy-path": "file_copy_path", "copy-link": "file_copy_link", reveal: "file_reveal", app: "file_open_app" });
// The name menu's tabs as telemetry names them: Files is the explorer.
const TAB_CONTROLS = Object.freeze({ models: "models", files: "explorer" });

/**
 * The row above a file and above the host's home in a page's chrome (`FileViewer`'s `chrome: "page"`,
 * the web viewer's): the same row whatever is open, so a person finds each control in the same place.
 * Over the home it has only the logo (its menu without Back to home), Back and Forward, the host's
 * update and its actions. A host that shows the view alone (`chrome: "bare"`: the CAD app's file
 * handler) has no navbar, and Preview hides it in every host, drawing its own bar in its place.
 *
 * Left, in this order: the text-to-cad logo (the C mark, over the home and over a document
 * alike), which opens the app's menu (`AppMenu`: Back to home
 * where the host has a home, then the person's settings, feedback and links); Back and Forward,
 * where the host keeps the view's own history (`history`), on a desktop's row alone (a phone's has
 * no room for them); the open document's name, which opens the name menu (Models, the host's library's models, and Files, the explorer)
 * where the view can show another; and the ⋯ menu of what can be done with the document: Copy path,
 * Open in (Browser, the file manager) and the host's own items (the CAD viewer's Export) — a model's
 * Copy path and file manager acting on its script. The menu and its submenus are shadcn's own width.
 *
 * Right, only what a host or a file adds, kept for the update's nudge, in this order: the file's own
 * actions (the CAD viewer's one: a dismissed alert's icon, which brings its card back); the host's own
 * actions (`actions`: the CAD app's Full size, inline); last, outermost, the host's update button
 * while its install is behind (`update`, the blue `UpdateButton` from `@text-to-cad/ui/update`).
 * The colour scheme is the app menu's. A view's own controls are never here: Display and Preview end its tool strip.
 *
 * Nothing here is drawn for its own sake: a control appears only where it does something.
 */

/**
 * The left of the row: the logo, the file's name and its ⋯, one kind of control — transparent until
 * the pointer is on it or its menu is open, then the same accent — and none with a tooltip: each
 * says what it is. They sit edge to edge, spaced by their own padding alone: the logo's 24px button,
 * Back, Forward and the ⋯ in 20px ones, the name 4px in from its edges — about 7px between glyphs.
 */
const NAV_ITEM_CLASS = "flex h-6 shrink-0 cursor-pointer items-center rounded-md outline-none transition-colors hover:bg-accent hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring/45 data-[state=open]:bg-accent data-[state=open]:text-accent-foreground";

/**
 * The text-to-cad logo, the app's menu: the "C" mark, 16px, the same over the home and over a
 * document (one mark, no wordmark and nothing that moves between the two); over the home its menu
 * has no Back to home. It is the way back to the home from every page.
 */
function LogoMenu({ onHome, menu }) {
  const { t } = useI18n();
  return <AppMenu onHome={onHome} {...menu} trigger={<button type="button" aria-label={t("navbar.menu")} className={cn(NAV_ITEM_CLASS, "cad-navbar-logo justify-start px-1")}
    data-navbar-menu="" data-logo="mark">
    <img src={logo} alt="" className="cad-navbar-mark" draggable={false} />
  </button>} />;
}

// Back and Forward: the row's icon buttons, muted as the ⋯ is, and dimmed where there is nowhere to go.
const HISTORY_CLASS = cn(NAV_ITEM_CLASS, "w-5 justify-center text-muted-foreground disabled:cursor-default disabled:opacity-40 disabled:hover:bg-transparent disabled:hover:text-muted-foreground");

/**
 * Back and Forward through the view's own history, as a browser's are: each disabled where it has
 * nowhere to go. The history is the host's (`viewHistory`), never the page's.
 */
function HistoryButtons({ viewHistory }) {
  const { t } = useI18n();
  const usage = useControlUsage();
  return <span className="flex shrink-0 items-center" data-navbar-history="">
    <button type="button" aria-label={t("navbar.back")} disabled={!viewHistory.canGoBack} onClick={() => { usage.used("navbar_back"); viewHistory.back(); }} className={HISTORY_CLASS}>
      <ArrowLeft className="size-3.5" aria-hidden="true" />
    </button>
    <button type="button" aria-label={t("navbar.forward")} disabled={!viewHistory.canGoForward} onClick={() => { usage.used("navbar_forward"); viewHistory.forward(); }} className={HISTORY_CLASS}>
      <ArrowRight className="size-3.5" aria-hidden="true" />
    </button>
  </span>;
}

// A disabled menu row, as shadcn's disabled item is: dimmed and deaf to the pointer (stock
// `DropdownMenuSubTrigger` has no disabled style of its own).
const DISABLED_ROW_CLASS = "data-[disabled]:pointer-events-none data-[disabled]:opacity-50";

/**
 * A disabled row with its reason as a hint. A disabled Radix item takes no pointer, so the hint is
 * on a wrapper that does, as shadcn hints a disabled button.
 */
function WhyDisabled({ reason, children }) {
  return <TooltipHint content={reason} side="right"><span className="block" data-disabled-reason="">{children}</span></TooltipHint>;
}

/**
 * The host's apps for the document's files (`fileMenu.apps`), asked each time the menu opens and never
 * before: null until they come, and null for good where the host has none, or fails or never answers
 * (the menu is then as without them). An answer to an opening since closed is dropped.
 */
function useOpenInApps(open, apps) {
  const [files, setFiles] = useState(null);
  useEffect(() => {
    if (!open || !apps) return undefined;
    const controller = new AbortController();
    setFiles(null);
    Promise.resolve().then(() => apps({ signal: controller.signal })).then(answer => {
      if (!controller.signal.aborted) setFiles(answer && Array.isArray(answer.targets) ? answer : null);
    }, () => {});
    return () => controller.abort();
  }, [open, apps]);
  return open ? files : null;
}

/**
 * The ⋯ after the file's name: what can be done with the document. Copy path (where its source is,
 * or was); Copy link (its page, with a fresh link: every document, its source there or not); Open in, a submenu of the places it opens in (`openInMenu`: the document's page in the
 * browser, the CAD app's, and the desktop's file manager by its name; then, once the host answers,
 * the source's apps, each export's apps and Default app, a separator between groups); then the
 * host's own items (`items`: the CAD viewer's Export submenu). Each only where the host can do it,
 * and no ⋯ where it can do none. While the source was moved or deleted, what opens it is drawn
 * disabled with the reason: Open in itself where nothing in it can open, else each such entry.
 */
function FileMenu({ platform, capabilities, sourceMissing = false, apps = null, onAction, items: hostItems = null }) {
  const { t } = useI18n();
  const usage = useControlUsage();
  const [open, setOpen] = useState(false);
  const files = useOpenInApps(open, apps);
  const copy = capabilities.has("copy-path");
  // A link to the page needs no source: always there where the host can make one.
  const copyLink = capabilities.has("copy-link");
  const openIn = openInMenu(platform, capabilities, t, { sourceMissing, files });
  if (!copy && !copyLink && !openIn.length && !hostItems) return null;
  const perform = (action, app) => { if (FILE_ACTION_CONTROLS[action]) usage.used(FILE_ACTION_CONTROLS[action]); onAction(action, app); };
  const openable = openIn.some(item => item.enabled);
  const label = t("file.openIn");
  const trigger = <DropdownMenuSubTrigger data-open-in-menu="" disabled={!openable} className={DISABLED_ROW_CLASS}>{label}</DropdownMenuSubTrigger>;
  return <DropdownMenu modal={false} open={open} onOpenChange={setOpen}>
    <DropdownMenuTrigger asChild><button aria-label={t("navbar.fileActions")} data-testid="file-actions" type="button"
      className={cn(NAV_ITEM_CLASS, "w-5 justify-center text-muted-foreground")}>
      <Ellipsis className="size-3.5" />
    </button></DropdownMenuTrigger>
    <DropdownMenuContent align="start" sideOffset={6}>
      {copy ? <DropdownMenuItem onSelect={() => perform("copy-path")}>{t("file.copyPath")}</DropdownMenuItem> : null}
      {copyLink ? <DropdownMenuItem onSelect={() => perform("copy-link")}>{t("file.copyLink")}</DropdownMenuItem> : null}
      {openIn.length ? <DropdownMenuSub>
        {openable ? trigger : <WhyDisabled reason={openIn.find(item => item.reason)?.reason}>{trigger}</WhyDisabled>}
        <DropdownMenuSubContent aria-label={label}>
          {openIn.map((item, index) => {
            const key = `${item.action}:${item.target ?? ""}:${item.app ?? ""}`;
            const choose = () => perform(item.action, item.action === "app" ? { target: item.target, app: item.app } : undefined);
            const row = <DropdownMenuItem data-open-in={item.action} data-open-in-app={item.app} disabled={!item.enabled} onSelect={choose}>{item.label}</DropdownMenuItem>;
            return <Fragment key={key}>
              {index && openIn[index - 1].group !== item.group ? <DropdownMenuSeparator /> : null}
              {item.enabled ? row : <WhyDisabled reason={item.reason}>{row}</WhyDisabled>}
            </Fragment>;
          })}
        </DropdownMenuSubContent>
      </DropdownMenuSub> : null}
      {hostItems}
    </DropdownMenuContent>
  </DropdownMenu>;
}

/**
 * What the name opens: Models and Files, two stock tabs sized to their labels on top of the
 * explorer's own style, each there only where the host has it (one alone has no tabs). Models is
 * the host's library's models, by last activity, a row opening its model; Files is the explorer
 * (`FolderExplorer`), from the file's folder, or for a model where the explorer was last. Built anew on each opening, on Models over a model and on Files over a file.
 */
function NameMenu({ path, kind, explorer, recent, onPick }) {
  const { t } = useI18n();
  const usage = useControlUsage();
  const [tab, setTab] = useState(() => firstTab(kind, explorer, recent));
  // The tab on screen as last chosen: a press and the focus it brings both ask for the same tab.
  const shownTab = useRef(tab);
  const files = explorer ? <FolderExplorer source={explorer.source} file={path} folder={explorer.folder} onFolderChange={explorer.onFolderChange}
    onOpen={next => onPick(explorer.onOpen, next)} /> : null;
  const models = recent ? <ModelList recent={recent} current={path} onOpen={next => { usage.used("models_open"); onPick(recent.onOpen, next); }} /> : null;
  if (!files || !models) return files ?? models;
  // A tab a person turns to is a use of it, as the one the menu opens on is (`FileName`).
  return <Tabs value={tab} onValueChange={next => { if (next !== shownTab.current) usage.used(TAB_CONTROLS[next]); shownTab.current = next; setTab(next); }} className="flex min-h-0 flex-1 flex-col gap-0" data-name-menu="">
    <TabsList className="mx-2 mt-2 h-7 w-fit shrink-0 self-start">
      <TabsTrigger value="models">{t("explorer.models")}</TabsTrigger>
      <TabsTrigger value="files">{t("explorer.files")}</TabsTrigger>
    </TabsList>
    <TabsContent value="models" className="flex min-h-0 flex-col">{models}</TabsContent>
    <TabsContent value="files" className="flex min-h-0 flex-col">{files}</TabsContent>
  </Tabs>;
}

/** The tab the name menu opens on: Models over a model, Files over a file, or the one there is. */
const firstTab = (kind, explorer, recent) => (!explorer ? "models" : !recent ? "files" : kind === "model" ? "models" : "files");

/**
 * The open document's name, with no glyph. Where the view can show another document it is also the
 * name menu's door: the name and its chevron, transparent until the pointer is on it, opening the
 * menu under it. Where it cannot, it is the name alone, in the same place.
 */
function FileName({ path, name: given, kind = "file", explorer, recent }) {
  const [open, setOpen] = useState(false);
  const mobile = useViewerMobile();
  const usage = useControlUsage();
  const name = given || path.split("/").pop() || path;
  if (!explorer && !recent) return <span className="flex min-w-0 items-center gap-1 px-1" data-file-name=""><span className="truncate">{name}</span></span>;
  // Opened, the tab's filter has the keyboard (the explorer's, or the Models tab's), so typing
  // finds a document at once; Down takes it into the rows. A phone keeps its keyboard down, the menu
  // holding focus itself. Nothing else is focused for the person on opening.
  const focusFilter = event => {
    event.preventDefault();
    const content = event.currentTarget;
    (mobile ? content : content.querySelector("input") ?? content).focus({ preventScroll: true });
  };
  const intoRows = event => {
    if (event.key !== "ArrowDown" || event.target !== event.currentTarget) return;
    const first = event.currentTarget.querySelector("[data-model-row]:not(:disabled), [data-explorer-row]");
    if (!first) return;
    event.preventDefault();
    first.focus();
  };
  const pick = (opener, next) => { setOpen(false); opener(next); };
  // Opened, the tab it opens on is a use of that tab (`usage/controls.js`: `models`, `explorer`).
  return <Popover open={open} onOpenChange={next => { if (next && !open) usage.used(TAB_CONTROLS[firstTab(kind, explorer, recent)]); setOpen(next); }}>
    <PopoverTrigger asChild>
      <button type="button" className={cn(NAV_ITEM_CLASS, "min-w-0 shrink gap-1 px-1 text-left")} data-file-name="">
        <span className="truncate">{name}</span>
        {/* The name opens its menu; the chevron says so. A plain name (no menu) has none. */}
        <ChevronDown className="ml-0.5 size-3 shrink-0 text-muted-foreground" aria-hidden="true" />
      </button>
    </PopoverTrigger>
    <PopoverContent align="start" sideOffset={8} data-file-explorer="" onOpenAutoFocus={focusFilter} onKeyDown={intoRows}
      className={cn(FLOATING_SURFACE_CLASS, "flex max-h-[min(28rem,var(--radix-popover-content-available-height))] w-[17.5rem] max-w-[calc(100vw-1rem)] flex-col overflow-hidden p-0")}>
      {/* Remounted on each opening, so it starts on its first tab, in the open file's folder. */}
      <NameMenu path={path} kind={kind} explorer={explorer} recent={recent} onPick={pick} />
    </PopoverContent>
  </Popover>;
}

/**
 * @param {object} props
 * @param {(() => void) | undefined} [props.onHome] The host's home, where it has one: the menu's Back to home.
 * @param {{ links?: import("../../host/types.js").ViewerLinks, appSettings?: readonly import("../types.js").AppSetting[], colorScheme?: import("../types.js").ColorSchemeSetting, platform?: string } | null} [props.menu]
 *   The rest of the app's menu: the host's links and the person's settings.
 * @param {import("../types.js").ViewerHistory | null} [props.history] The view's own history, where the host keeps one: Back and Forward after the logo.
 * @param {string | null} [props.file] The open file, by its absolute path (a document with no file of its own: its id).
 * @param {string} [props.name] The document's name where its path does not give it (a model's).
 * @param {"model" | "file"} [props.kind] What the open document is: its glyph, and the name menu's first tab.
 * @param {{ source: Pick<import("../types").FileSource, "list" | "search">, folder?: string | null, onOpen(path: string): void } | null} [props.explorer]
 *   Where the host's files can be browsed: the name menu's Files, from `folder` where given.
 * @param {{ list(): Promise<readonly import("../types").RecentDocument[]>, onOpen(path: string): void } | null} [props.recent]
 *   The host's library: the name menu's Models, its models alone.
 * @param {{ platform: import("./entry-menu.js").Platform, capabilities: ReadonlySet<import("./entry-menu.js").EntryAction>, sourceMissing?: boolean,
 *   apps?: (options: { signal: AbortSignal }) => Promise<import("./entry-menu.js").OpenInFiles | null>,
 *   onAction(action: import("./entry-menu.js").EntryAction | "app", app?: { target: string, app: string }): void, items?: import("react").ReactNode } | null} [props.fileMenu]
 *   The ⋯ after the name: what the host can do with the document on screen, and its own items (Export).
 * @param {import("react").ReactNode} [props.trailing] The file's actions.
 * @param {import("react").ReactNode} [props.actions] The host's own controls at the right end (the CAD app's Full size).
 * @param {import("react").ReactNode} [props.update] The host's update button, last among the controls (outermost).
 * @param {string} [props.className]
 */
export function ViewerNavbar({ onHome: goHome, menu = null, history = null, file = null, name, kind = "file", explorer = null, recent = null, fileMenu = null, trailing = null, update = null, actions = null, className }) {
  const { t } = useI18n();
  const usage = useControlUsage();
  const onHome = goHome ? () => { usage.used("home"); goHome(); } : goHome;
  const mobile = useViewerMobile();
  return (
    // `pl-3`: the logo's mark (its button's 4px in) stands on the page's 16px gutter, the Home's
    // grid's left edge (`.cad-library-content`), over the home and over a page alike.
    <header className={cn(NAVBAR_ROW_CLASS, "pl-3 border-border bg-background text-foreground", className)} data-viewer-navbar="">
      <nav aria-label={t("navbar.viewer")} className="flex min-w-0 flex-1 items-center overflow-hidden text-sm">
        {onHome || menu ? <LogoMenu onHome={onHome} menu={menu} /> : null}
        {/* A phone's row has no room for them: Back and Forward are a desktop's alone. */}
        {history && !mobile ? <HistoryButtons viewHistory={history} /> : null}
        {file ? <span className="flex min-w-0 items-center">
          <FileName path={file} name={name} kind={kind} explorer={explorer} recent={recent} />
          {fileMenu ? <FileMenu {...fileMenu} /> : null}
        </span> : null}
      </nav>
      <div className={NAVBAR_CONTROLS_CLASS}>
        {trailing}
        {actions}
        {update}
      </div>
    </header>
  );
}
