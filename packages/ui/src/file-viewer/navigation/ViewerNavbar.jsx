import { ArrowLeft, ArrowRight, Ellipsis, Folder, Search } from "lucide-react";
import { useLayoutEffect, useRef, useState } from "react";

import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuShortcut, DropdownMenuSub, DropdownMenuSubContent, DropdownMenuSubTrigger, DropdownMenuTrigger } from "@cad/ui/primitives/dropdown-menu";
import { TooltipHint } from "@cad/ui/primitives/tooltip";
import { ToolbarButton } from "@cad/ui/primitives/toolbar-button";
import { useI18n } from "@cad/ui/i18n";
import { isDocumentId } from "@cad/core/lib/cadRefs.js";
import { cn } from "@cad/ui/utils";

import logo from "../../assets/logo-c.svg";
import { NAVBAR_CONTROLS_CLASS, NAVBAR_ROW_CLASS } from "../../lib/navbarRow.js";
import { useViewerMobile } from "../responsive.js";

import { AppMenu } from "./AppMenu.jsx";
import { OpenInItems, WhyDisabled, useOpenInApps } from "./OpenInItems.jsx";
import { openInMenu } from "./entry-menu.js";
import { useControlUsage } from "../../usage/controls.js";
import { prefersCoarsePointer } from "../../lib/coarsePointer.js";

// The file menu's items as telemetry names them (`usage/controls.js`): an app chosen in Open in is
// `file_open_app`, never which app; Open in's Browser is counted by none.
const FILE_ACTION_CONTROLS = Object.freeze({ "copy-path": "file_copy_path", "copy-link": "file_copy_link", reveal: "file_reveal", app: "file_open_app" });

/**
 * The row above a file and above the host's home, in every host: the same row whatever is open, so a
 * person finds each control in the same place. Over the home it has only the logo, the panel's toggle,
 * Back and Forward, the home's own controls, the host's actions and its update button. Preview hides it, drawing its
 * own bar in its place, and a compact view (a small inline view) has none.
 *
 * Left, in this order: the text-to-cad logo (the C mark, over the home and over a document alike), always first, so the
 * way home stands in one place on every page: where the host has a home (`onHome`) a link to it (Recents; a real link
 * where the host gives it an address, `homeHref`), a button otherwise, with a hint saying so; where it has none (a view
 * that shows one file alone), the button that opens the app's menu (`AppMenu`: the person's settings, feedback and
 * links, which a host with a home keeps in the panel's foot, `../PanelFoot.jsx`, at the bottom of the sidebar on the
 * home and over a document); the panel's toggle, over a file with a panel and over the home, whose sidebar is the same
 * panel (below); Back and Forward,
 * where the host keeps the view's own history (`history`), on a desktop's row alone (a phone's has
 * no room for them); where the document is in a project, the project's name and a slash, muted, which goes to the
 * home at that project (`project`: Figma's location before a file's name; a folder tile in a narrow row and on a
 * phone); the open document's name; and the ⋯ menu of what can be done with the document: Copy path, Open in new tab,
 * Open in (Browser, the file manager), the host's own items (the viewer's Export), then Search documents with its key
 * (`search/DocumentSearch.tsx`: the way to any other document), Previous and Next in project and, for a document in no
 * project, Import its folder as a project — a model's Copy path and file manager acting on its script. The menu and
 * its submenus are shadcn's own width.
 *
 * The panel's toggle (`panels.left`, which the panel's frame says: `../panelToggles.js`), right after the logo, over a
 * file that has a panel and over the home; the strip's 28px tile, the same neutral button open or shut, its tooltip
 * naming its key. It comes second because it is there only where the page has a panel: first, it would move the logo
 * on every page that has none.
 *
 * Right, only what a host or a file adds, in this order: the file's own actions (the viewer's
 * one: a dismissed alert's icon, which brings its card back); the view's own controls, Display (the plain cube) then,
 * where the view has it, Preview, which the view on screen portals into the row's view slot (`../navbarSlots.js`);
 * the host's own actions (`actions`: the CAD app's Full size, inline); last, outermost, the host's update button
 * while its install is behind or an update is underway or failed (`update`, the blue `UpdateButton` from `@cad/ui/update`).
 * The colour scheme is the app menu's.
 *
 * Nothing here is drawn for its own sake: a control appears only where it does something.
 */

/**
 * The left of the row: the logo, the file's name and its ⋯, one kind of control — transparent until
 * the pointer is on it or its menu is open, then the same accent. The name and the ⋯ have no tooltip: each
 * says what it is. They sit edge to edge, spaced by their own padding alone, on a desktop and a phone alike: the logo,
 * Back, Forward and the ⋯ in the control's tiles (the tool strip's: 28px, a phone's 36px), the name's text a control's
 * padding less 4px in from its edges (4px, a phone's 6px). Their fill is `hover:` (only where the pointer hovers) or an open
 * menu's, their ring `focus-visible:`, so a tap leaves neither.
 */
const NAV_ITEM_CLASS = "flex h-control shrink-0 cursor-pointer items-center rounded-md outline-none transition-colors hover:bg-accent hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring/45 data-[state=open]:bg-accent data-[state=open]:text-accent-foreground";
// The mark centred in its tile, as padding (half the control less the 16px mark): a desktop's 6px, the 16px line.
const LOGO_CLASS = cn(NAV_ITEM_CLASS, "cad-navbar-logo w-control justify-start px-[calc((var(--cad-control)-16px)/2)]", "no-underline");

/**
 * The text-to-cad logo: the "C" mark, 16px, the same over the home and over a document (one mark, no wordmark and
 * nothing that moves between the two), in one control that never changes place.
 *
 * Where the host has a home (`onHome`) it is the way home, from every page: a real link where the host gives the home
 * an address (`href`: a plain click goes home in this view, and ⌘ or Ctrl and a click, a middle click or the link's
 * own menu are the browser's), a button otherwise, named "Home" and saying so in a hint. Over the home it goes to
 * Recents. It opens no menu there: the links and Settings are the panel's foot's (`../PanelFoot.jsx`).
 *
 * Where the host has no home (a view that shows one file alone) there is no foot, so the logo
 * opens the app's menu itself (`menu`), with no hint: a menu's button says what it is by opening.
 */
function Logo({ onHome = null, href = null, menu = null }) {
  const { t } = useI18n();
  const mark = <img src={logo} alt="" className="cad-navbar-mark" draggable={false} />;
  if (!onHome) return <AppMenu {...menu} trigger={<button type="button" aria-label={t("navbar.menu")} className={LOGO_CLASS}
    data-navbar-logo="menu" data-navbar-menu="" data-logo="mark">{mark}</button>} />;
  const label = t("home.title");
  const Element = href ? "a" : "button";
  const own = href ? { href } : { type: "button" };
  return <TooltipHint content={label}><Element {...own} aria-label={label} className={LOGO_CLASS} data-navbar-logo="home" data-logo="mark"
    onClick={event => {
      // A modified or a middle click on the link is the browser's: the home in a new tab or window.
      if (href && (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey || event.button !== 0)) return;
      event.preventDefault();
      onHome();
    }}>{mark}</Element></TooltipHint>;
}

// Back and Forward: the row's icon buttons, muted as the ⋯ is, and dimmed where there is nowhere to go.
const HISTORY_CLASS = cn(NAV_ITEM_CLASS, "w-control justify-center text-muted-foreground disabled:cursor-default disabled:opacity-40 disabled:hover:bg-transparent disabled:hover:text-muted-foreground");

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
 * The ⋯ after the file's name: what can be done with the document, from the document itself outwards. Copy path (where
 * its source is, or was); Copy link (its page, with a fresh link: every document, its source there or not); then where
 * it opens: Open in new tab (`beside`: its page beside this view, "Open in browser" from an app's frame; none where it
 * would be Open in's Browser again), then Open in, a submenu of the places it opens in (`openInMenu`: the document's
 * page in the browser, the CAD app's, and the desktop's file manager by its name; then, once the host answers, the
 * source's apps, each export's apps and Default app, a separator between groups); then what is made from it, the host's
 * own items (`items`: the viewer's Export submenu); last, after a separator, the way to other documents and its
 * project, one group: Search documents (`search`: the search of every document, its key at the right; every document
 * where the host has a library), then for a document in a project of more than one document, Previous in project and
 * Next in project (`neighbours`, each disabled at its end, their keys `[` and `]` at the right), and for a document in
 * none, Import its folder as a project (`onImportFolder`: the desktop's chooser, starting at its folder, so the person
 * picks the level). Each only where the host can do it, and no ⋯ where
 * it can do none. While the source was moved or deleted, what opens it is drawn disabled with the reason: Open in
 * itself where nothing in it can open, else each such entry.
 */
function FileMenu({ platform, capabilities, sourceMissing = false, apps = null, onAction, items: hostItems = null, onImportFolder = null, beside = null, neighbours = null, search = null }) {
  const { t } = useI18n();
  const usage = useControlUsage();
  const [open, setOpen] = useState(false);
  const files = useOpenInApps(open, apps);
  const copy = capabilities.has("copy-path");
  // A link to the page needs no source: always there where the host can make one.
  const copyLink = capabilities.has("copy-link");
  const openIn = openInMenu(platform, capabilities, t, { sourceMissing, files });
  if (!copy && !copyLink && !openIn.length && !hostItems && !onImportFolder && !beside && !neighbours && !search) return null;
  // A touch screen has no keys to hint at.
  const keys = !prefersCoarsePointer();
  const perform = (action, app) => { if (FILE_ACTION_CONTROLS[action]) usage.used(FILE_ACTION_CONTROLS[action]); onAction(action, app); };
  const openable = openIn.some(item => item.enabled);
  const label = t("file.openIn");
  const trigger = <DropdownMenuSubTrigger data-open-in-menu="" disabled={!openable} className={DISABLED_ROW_CLASS}>{label}</DropdownMenuSubTrigger>;
  return <DropdownMenu modal={false} open={open} onOpenChange={setOpen}>
    <DropdownMenuTrigger asChild><button aria-label={t("navbar.fileActions")} data-testid="file-actions" type="button"
      className={cn(NAV_ITEM_CLASS, "w-control justify-center text-muted-foreground")}>
      <Ellipsis className="size-3.5" />
    </button></DropdownMenuTrigger>
    <DropdownMenuContent align="start" sideOffset={6}>
      {copy ? <DropdownMenuItem onSelect={() => perform("copy-path")}>{t("file.copyPath")}</DropdownMenuItem> : null}
      {copyLink ? <DropdownMenuItem onSelect={() => perform("copy-link")}>{t("file.copyLink")}</DropdownMenuItem> : null}
      {beside ? <DropdownMenuItem onSelect={beside.onSelect} data-open-beside="">{beside.label}</DropdownMenuItem> : null}
      {openIn.length ? <DropdownMenuSub>
        {openable ? trigger : <WhyDisabled reason={openIn.find(item => item.reason)?.reason}>{trigger}</WhyDisabled>}
        <DropdownMenuSubContent aria-label={label}>
          <OpenInItems entries={openIn} onChoose={item => perform(item.action, item.action === "app" ? { target: item.target, app: item.app } : undefined)} />
        </DropdownMenuSubContent>
      </DropdownMenuSub> : null}
      {hostItems}
      {/* The last group: the way to other documents (the search of them all, the project's previous and next), and a
          standalone document's way into a project. */}
      {search || neighbours || onImportFolder ? <>
        {copy || copyLink || beside || openIn.length || hostItems ? <DropdownMenuSeparator /> : null}
        {search ? <DropdownMenuItem data-menu-search="" onSelect={search.onSelect}><Search aria-hidden="true" />
          {t("search.menu")}{keys && search.shortcut ? <DropdownMenuShortcut>{search.shortcut}</DropdownMenuShortcut> : null}</DropdownMenuItem> : null}
        {neighbours ? <>
          <DropdownMenuItem data-project-previous="" disabled={!neighbours.previous} onSelect={() => neighbours.previous?.()}>
            {t("project.previous")}{keys ? <DropdownMenuShortcut>[</DropdownMenuShortcut> : null}</DropdownMenuItem>
          <DropdownMenuItem data-project-next="" disabled={!neighbours.next} onSelect={() => neighbours.next?.()}>
            {t("project.next")}{keys ? <DropdownMenuShortcut>]</DropdownMenuShortcut> : null}</DropdownMenuItem>
        </> : null}
        {onImportFolder ? <DropdownMenuItem data-import-folder="" disabled={sourceMissing} onSelect={() => { usage.used("file_import_folder"); onImportFolder(); }}>
          {t("project.importFolder")}</DropdownMenuItem> : null}
      </> : null}
    </DropdownMenuContent>
  </DropdownMenu>;
}

/**
 * The open document's name, with no glyph: until the host knows it, a file's path's last segment; a document named by
 * its id is never named by the id, its name's place empty until its name is known. After a project's name (`after`) it
 * keeps its width, up to 65% of the row's, and the project's name gives way instead.
 */
function FileName({ path, name: given, after = false }) {
  const name = given || (isDocumentId(path) ? "" : path.split("/").pop() || path);
  return <span className={cn("flex min-w-0 items-center gap-1", after && "max-w-[65%] shrink-0", "px-[calc(var(--cad-pad)-4px)]")} data-file-name=""><span className="truncate">{name}</span></span>;
}

/** The least room the project's name keeps as text: under it (and on a phone) it is the folder tile instead. */
const CRUMB_LEAST_PX = 80;

/**
 * Whether the project's name is the folder tile: always on a phone, and on a desktop's row while the room it has (its
 * own width and whatever the row has left over) is under `CRUMB_LEAST_PX`, or under its whole name where that is
 * shorter. The room is the same drawn either way, so the choice holds still; measured as the row or the name changes.
 */
function useCrumbTile(wrapper, measurer, mobile, name) {
  const [tile, setTile] = useState(false);
  useLayoutEffect(() => {
    const element = wrapper.current, nav = element?.closest("nav");
    if (mobile || !element || !nav) return undefined;
    const measure = () => {
      const control = element.firstElementChild?.getBoundingClientRect().width ?? 0;
      // What the row has left after its last control (less than nothing where they overflow it).
      const left = nav.getBoundingClientRect().right - (nav.lastElementChild?.getBoundingClientRect().right ?? 0);
      const room = control + left;
      const whole = measurer.current?.getBoundingClientRect().width ?? 0;
      setTile(room < Math.min(whole, CRUMB_LEAST_PX));
    };
    measure();
    if (typeof ResizeObserver === "undefined") return undefined;
    const observer = new ResizeObserver(measure);
    observer.observe(nav);
    const named = nav.querySelector("[data-file-name]");
    if (named) observer.observe(named);
    return () => observer.disconnect();
  }, [wrapper, measurer, mobile, name]);
  return mobile || tile;
}

/**
 * The project a document is in, before its name (`project / document`): the project's name, muted, which goes to the
 * home at that project, then a slash. Where the host gives the project's page an address (`href`) it is a real link: a
 * plain click is `onOpen` (in this view), and ⌘ or Ctrl and a click, a middle click or the link's own menu open the
 * page in a new tab, the browser's own. In a narrow row it truncates down to `CRUMB_LEAST_PX`, and under that, and on a
 * phone, it is a control-sized folder tile named by the project (its name in a hint), so the way to the project is
 * never lost; the document's name keeps its width either way.
 */
function ProjectCrumb({ project }) {
  const usage = useControlUsage();
  const mobile = useViewerMobile();
  const wrapper = useRef(null), measurer = useRef(null);
  const tile = useCrumbTile(wrapper, measurer, mobile, project.name);
  const onClick = event => {
    if (project.href && (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey || event.button !== 0)) return;
    event.preventDefault();
    usage.used("project_crumb");
    project.onOpen();
  };
  const Element = project.href ? "a" : "button";
  const own = project.href ? { href: project.href } : { type: "button" };
  const control = tile
    ? <TooltipHint content={project.name}><Element {...own} aria-label={project.name} onClick={onClick} data-project-tile=""
      className={cn(NAV_ITEM_CLASS, "w-control justify-center text-muted-foreground")}><Folder className="size-4" aria-hidden="true" /></Element></TooltipHint>
    : <Element {...own} onClick={onClick} className={cn(NAV_ITEM_CLASS, "min-w-0 shrink text-muted-foreground", "px-[calc(var(--cad-pad)-4px)]")}>
      <span className="truncate">{project.name}</span></Element>;
  return <span ref={wrapper} className={cn("relative flex min-w-0 items-center", tile ? "shrink-0" : "shrink")} data-navbar-project="">
    {control}
    <span className="shrink-0 text-muted-foreground" aria-hidden="true">/</span>
    {/* The whole name as the text would draw it, out of sight: what the tile weighs the room against (a desktop's). */}
    {mobile ? null : <span ref={measurer} aria-hidden="true" className="pointer-events-none invisible absolute top-0 left-0 whitespace-nowrap px-[calc(var(--cad-pad)-4px)]">{project.name}</span>}
  </span>;
}

// The home's row is a size container (`cad-navbar`), so its search folds to its icon on the row's width, not the window's.
const HOME_ROW_STYLE = Object.freeze({ containerType: "inline-size", containerName: "cad-navbar" });

/**
 * The sidebar's glyph, as Claude Code's: a rounded rectangle (14 × 12 in the 16px box, its corners 3px) and a short
 * line inside it near its left edge, half the rectangle's height, centred; lucide's stroke, so it weighs what the
 * row's other icons weigh. The same open or shut: the panel itself says which.
 */
export function SidebarIcon(props) {
  return <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth={1.33} strokeLinecap="round"
    strokeLinejoin="round" aria-hidden="true" data-sidebar-icon="" {...props}>
    <rect x="1" y="2" width="14" height="12" rx="3" />
    <path d="M5 5v6" />
  </svg>;
}

/**
 * The panel's toggle, right after the logo: the strip's 28px tile, the same neutral button whether its panel is
 * open or shut (no pressed fill: the panel beside the model says which), its state said to assistive technology
 * (`aria-expanded`, the panel pinned open or not; a peek is not said), its tooltip its name ("Hide panel", "Show panel")
 * and its key, at its right, on the navbar's row, so it never stands over the panel peeking under it. A mouse resting
 * on it peeks the collapsed panel (`toggle.hover`, the frame's `usePanelPeek.js`); once the peek is up its tooltip goes,
 * and stays away while it is (`toggle.peeking`): the panel is showing, which is what the tip offered.
 */
function PanelToggleButton({ toggle }) {
  return <ToolbarButton label={toggle.label} shortcut={toggle.shortcut || ""} tooltipSide="right" expandedTooltip tooltipHidden={toggle.peeking === true}
    aria-expanded={toggle.open} aria-disabled={toggle.disabled || undefined} onClick={toggle.disabled ? undefined : toggle.toggle} {...(toggle.hover ?? null)}
    className="size-control shrink-0 rounded-md text-muted-foreground [&>svg]:size-4!" data-navbar-panel="left">
    <SidebarIcon />
  </ToolbarButton>;
}

/**
 * @param {object} props
 * @param {(() => void) | undefined} [props.onHome] The host's home, where it has one: the logo goes to it (Recents).
 * @param {string | null} [props.homeHref] The home's own address, where the host gives it one: the logo is then a real link.
 * @param {{ links?: import("../../host/types.js").ViewerLinks, appSettings?: readonly import("../types.js").AppSetting[], colorScheme?: import("../types.js").ColorSchemeSetting,
 *   language?: import("../types.js").LanguageSetting, platform?: string } | null} [props.menu]
 *   The app's menu, where the host has no home (`onHome` absent): the logo opens it. A host with a home keeps it in
 *   the panel's foot (`../PanelFoot.jsx`), and the navbar draws none.
 * @param {import("../types.js").ViewerHistory | null} [props.history] The view's own history, where the host keeps one: Back and Forward after the logo.
 * @param {string | null} [props.file] The open file, by its absolute path (a document with no file of its own: its id).
 * @param {string} [props.name] The document's name where its path does not give it (a model's).
 * @param {{ name: string, href?: string | null, onOpen(): void } | null} [props.project] The project the document is in: its
 *   name before the document's, which goes to the home at that project (a link where `href` gives its page's address).
 * @param {{ platform: import("./entry-menu.js").Platform, capabilities: ReadonlySet<import("./entry-menu.js").EntryAction>, sourceMissing?: boolean,
 *   apps?: (options: { signal: AbortSignal }) => Promise<import("./entry-menu.js").OpenInFiles | null>,
 *   onAction(action: import("./entry-menu.js").EntryAction | "app", app?: { target: string, app: string }): void, items?: import("react").ReactNode,
 *   onImportFolder?: (() => void) | null, beside?: { label: string, onSelect(): void } | null,
 *   neighbours?: { previous: (() => void) | null, next: (() => void) | null } | null,
 *   search?: { onSelect(): void, shortcut?: string } | null } | null} [props.fileMenu]
 *   The ⋯ after the name: what the host can do with the document on screen, its own items (Export), then Search
 *   documents with its key where the host has the search, and for a document in a project, Previous and Next in
 *   project; in none, Import its folder as a project.
 * @param {import("react").ReactNode} [props.trailing] The file's actions.
 * @param {import("react").ReactNode} [props.actions] The host's own controls at the right end (the CAD app's Full size).
 * @param {import("react").ReactNode} [props.update] The host's update button, last among the controls (outermost).
 * @param {{ right(element: HTMLElement | null): void } | null} [props.homeSlots]
 *   Over the home: where its controls go (`../navbarSlots.js`), a slot at the row's right end. The home's place says
 *   where the person is in its own title, so the row holds no name of the home's.
 * @param {{ left?: { open: boolean, label: string, shortcut?: string, toggle(): void, hover?: object | null } | null } | null} [props.panels]
 *   The panel's toggle, where the page has a panel (`../panelToggles.js`): a file's view's, and the home's sidebar's.
 * @param {((element: HTMLElement | null) => void) | null} [props.viewSlot] Over a file: where its view puts its view settings
 *   (`../navbarSlots.js`'s `NavbarViewSlotContext`).
 * @param {string} [props.className]
 */
export function ViewerNavbar({ onHome: goHome, homeHref = null, menu = null, history = null, file = null, name, project = null, fileMenu = null, trailing = null, actions = null, update = null, panels = null, homeSlots = null, viewSlot = null, className }) {
  const { t } = useI18n();
  const usage = useControlUsage();
  const onHome = goHome ? () => { usage.used("home"); goHome(); } : goHome;
  const mobile = useViewerMobile();
  const header = useRef(null), lead = useRef(null), trail = useRef(null);
  const homing = Boolean(homeSlots && !file);
  // The row's controls at THE scale (`globals.css`), one rule on a desktop and a phone: the logo, the toggle, the name
  // and its ⋯, edge to edge, each the control tall, every icon centred in its tile.
  const leadNav = <nav ref={lead} aria-label={t("navbar.viewer")} className={cn("flex min-w-0 items-center overflow-hidden text-sm", homing ? "shrink-0" : "flex-1")}>
    {/* The logo first, on every page, so the way home never moves; then the panel's toggle where the page has a panel
        (a file's, the home's sidebar), edge to edge with it as the row's other controls are. */}
    {onHome || menu ? <Logo onHome={onHome} href={homeHref} menu={menu} /> : null}
    {panels?.left ? <span className="flex shrink-0 items-center"><PanelToggleButton toggle={panels.left} /></span> : null}
    {/* A phone's row has no room for them: Back and Forward are a desktop's alone. */}
    {history && !mobile ? <HistoryButtons viewHistory={history} /> : null}
    {file ? <span className="flex min-w-0 items-center">
      {project ? <ProjectCrumb project={project} /> : null}
      <FileName path={file} name={name} after={Boolean(project)} />
      {fileMenu ? <FileMenu {...fileMenu} /> : null}
    </span> : null}
  </nav>;
  return (
    // The logo's drawn mark, the row's first glyph on every page, stands on the page's 16px gutter, the
    // Home's grid's left edge (`.cad-library-content`) and the view's panel's 16px line: the row's 8px,
    // its button's 6px, and the 2px the mark's artwork sits in from its 16px image's edge.
    // On the chrome's colour, a step off the canvas's (`--sidebar`: lighter than white's off-white, a
    // step above the dark canvas), as the panel beside a board or a model is: the frame reads as frame.
    <header ref={header} className={cn(NAVBAR_ROW_CLASS, "relative border-border bg-sidebar text-foreground", className)} data-viewer-navbar=""
      style={homing ? HOME_ROW_STYLE : undefined}>
      {leadNav}
      {/* Over the home: the search and Import at the row's right. No "Home" after the logo and the toggle: the place's
          title says where the person is, and the logo is the way home. */}
      {homing ? <div className="flex min-w-0 flex-1 items-center justify-end gap-2" data-navbar-home="">
        <div ref={homeSlots.right} className="flex shrink-0 items-center gap-2" data-navbar-home-right="" />
      </div> : null}
      <div ref={trail} className={cn(NAVBAR_CONTROLS_CLASS, homing && "empty:hidden")}>
        {trailing}
        {/* The view's settings, the view's own (Display, then Preview where the view has it), portalled
            in by the view on screen (`../navbarSlots.js`); before the host's actions. */}
        {file && viewSlot ? <div ref={viewSlot} className="flex shrink-0 items-center gap-0.5 empty:hidden" data-navbar-view="" /> : null}
        {actions}
        {update}
      </div>
    </header>
  );
}
