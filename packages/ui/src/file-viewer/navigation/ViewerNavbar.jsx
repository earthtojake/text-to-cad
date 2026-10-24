import { ArrowLeft, ArrowRight, ChevronDown, Ellipsis } from "lucide-react";
import { useState } from "react";

import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@text-to-cad/ui/primitives/dropdown-menu";
import { Popover, PopoverContent, PopoverTrigger } from "@text-to-cad/ui/primitives/popover";
import { useI18n } from "@text-to-cad/ui/i18n";
import { cn } from "@text-to-cad/ui/utils";

import logo from "../../assets/logo-c.svg";
import { NAVBAR_CONTROLS_CLASS, NAVBAR_ROW_CLASS } from "../../lib/navbarRow.js";
import { FLOATING_SURFACE_CLASS } from "../../lib/floatingSurface.js";
import { useViewerMobile } from "../responsive.js";

import { AppMenu } from "./AppMenu.jsx";
import { entryMenu } from "./entry-menu.js";
import { FolderExplorer } from "./FolderExplorer.jsx";

/**
 * The row above a file and above the host's home: ONE navbar, the same in every app, so a person
 * finds each control in the same place whatever is open. Over the home it has only the logo (its
 * menu without Back to files), Back and Forward, the host's update, Full size and its page elsewhere.
 *
 * Left, in this order: the text-to-cad logo, which opens the app's menu (`AppMenu`: Back to files
 * where the host has a home, then the person's settings, feedback and links); Back and Forward,
 * where the host keeps the view's own history (`history`); the open file's name, which opens the
 * file explorer where the host's files can be browsed; and the ⋯ menu of what the host can do with
 * the file.
 *
 * Right, only what a host or a file adds: the host's update button while its install is behind
 * (`update`, the blue `UpdateButton` from `@text-to-cad/ui/update`); the file's own actions (the
 * CAD viewer's one: a dismissed alert's icon, which brings its card back); the host's way to show
 * the view full size (`fullSize`), where it shows it small; the renderer's own view controls,
 * drawn into the box it is handed (`controlsRef`: a 3D view's Display and Preview, or in Preview
 * its settings and the way out); last, the host's way to open what is shown in a page of its own
 * outside the host (`openInBrowser`: the CAD app's Open in browser). The colour scheme is the app menu's.
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

/** The text-to-cad logo, the size of the row's other icon buttons: the app's menu. */
function LogoMenu({ onHome, menu }) {
  const { t } = useI18n();
  return <AppMenu onHome={onHome} {...menu} trigger={<button type="button" aria-label={t("navbar.menu")} className={cn(NAV_ITEM_CLASS, "w-6 justify-center")} data-navbar-menu="">
    <img src={logo} alt="" className="size-4" draggable={false} />
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
  return <span className="flex shrink-0 items-center" data-navbar-history="">
    <button type="button" aria-label={t("navbar.back")} disabled={!viewHistory.canGoBack} onClick={() => viewHistory.back()} className={HISTORY_CLASS}>
      <ArrowLeft className="size-3.5" aria-hidden="true" />
    </button>
    <button type="button" aria-label={t("navbar.forward")} disabled={!viewHistory.canGoForward} onClick={() => viewHistory.forward()} className={HISTORY_CLASS}>
      <ArrowRight className="size-3.5" aria-hidden="true" />
    </button>
  </span>;
}

/** The ⋯ after the file's name: what the host can do with the file. A host that can do nothing has none. */
function FileMenu({ path, platform, capabilities, onAction }) {
  const { t } = useI18n();
  const items = entryMenu(platform, capabilities, t);
  if (!items.length) return null;
  return <DropdownMenu modal={false}>
    <DropdownMenuTrigger asChild><button aria-label={t("navbar.fileActions")} data-testid="file-actions" type="button"
      className={cn(NAV_ITEM_CLASS, "w-5 justify-center text-muted-foreground")}>
      <Ellipsis className="size-3.5" />
    </button></DropdownMenuTrigger>
    <DropdownMenuContent align="start" className="w-56" sideOffset={6}>
      {items.map(item => <DropdownMenuItem key={item.action} onSelect={() => onAction(item.action, path)}>{item.label}</DropdownMenuItem>)}
    </DropdownMenuContent>
  </DropdownMenu>;
}

/**
 * The open file's name. Where the host's files can be browsed it is also the explorer's door: the
 * name, transparent until the pointer is on it, opening the explorer under it. Where they cannot,
 * it is the name alone, in the same place.
 */
function FileName({ path, name: given, explorer }) {
  const [open, setOpen] = useState(false);
  const mobile = useViewerMobile();
  const name = given || path.split("/").pop() || path;
  if (!explorer) return <span className="min-w-0 truncate px-1" data-file-name="">{name}</span>;
  // Opened, its filter has the keyboard, so typing finds a file at once; a phone keeps its keyboard
  // down, the explorer holding focus itself. Nothing else is focused for the person on opening.
  const focusFilter = event => {
    event.preventDefault();
    const content = event.currentTarget;
    (mobile ? content : content.querySelector("input") ?? content).focus({ preventScroll: true });
  };
  return <Popover open={open} onOpenChange={setOpen}>
    <PopoverTrigger asChild>
      <button type="button" className={cn(NAV_ITEM_CLASS, "min-w-0 shrink px-1 text-left")} data-file-name="">
        <span className="truncate">{name}</span>
        {/* The name opens the explorer; the chevron says so. A plain name (no explorer) has none. */}
        <ChevronDown className="ml-0.5 size-3 shrink-0 text-muted-foreground" aria-hidden="true" />
      </button>
    </PopoverTrigger>
    <PopoverContent align="start" sideOffset={8} data-file-explorer="" onOpenAutoFocus={focusFilter}
      className={cn(FLOATING_SURFACE_CLASS, "flex max-h-[min(28rem,var(--radix-popover-content-available-height))] w-72 max-w-[calc(100vw-1rem)] flex-col overflow-hidden p-0")}>
      {/* Remounted on each opening, so it starts in the open file's folder. */}
      <FolderExplorer source={explorer.source} file={path} onOpen={next => { setOpen(false); explorer.onOpen(next); }} />
    </PopoverContent>
  </Popover>;
}

/**
 * @param {object} props
 * @param {(() => void) | undefined} [props.onHome] The host's home, where it has one: the menu's Back to files.
 * @param {{ links?: import("../../host/types.js").ViewerLinks, appSettings?: readonly import("../types.js").AppSetting[], colorScheme?: import("../types.js").ColorSchemeSetting, platform?: string } | null} [props.menu]
 *   The rest of the app's menu: the host's links and the person's settings.
 * @param {import("../types.js").ViewerHistory | null} [props.history] The view's own history, where the host keeps one: Back and Forward after the logo.
 * @param {string | null} [props.file] The open file, by its absolute path (a document with no file of its own: its id).
 * @param {string} [props.name] The document's name where its path does not give it (a model's).
 * @param {{ source: Pick<import("../types").FileSource, "list" | "search">, onOpen(path: string): void } | null} [props.explorer]
 *   Where the host's files can be browsed: the explorer the name opens.
 * @param {{ platform: import("./entry-menu.js").Platform, capabilities: ReadonlySet<import("./entry-menu.js").EntryAction>,
 *   onAction(action: import("./entry-menu.js").EntryAction, path: string): void } | null} [props.fileMenu]
 * @param {import("react").ReactNode} [props.trailing] The file's actions.
 * @param {import("react").ReactNode} [props.actions] Host workflow controls at the right end.
 * @param {import("react").ReactNode} [props.update] The host's update button, first among the controls.
 * @param {import("react").ReactNode} [props.fullSize] The host's Full size button, where it shows the view small.
 * @param {import("react").ReactNode} [props.openInBrowser] The host's way to open what is shown outside it, last in the row.
 * @param {(element: HTMLDivElement | null) => void} [props.controlsRef] The box the renderer draws its view controls into.
 * @param {string} [props.className]
 */
export function ViewerNavbar({ onHome, menu = null, history = null, file = null, name, explorer = null, fileMenu = null, trailing = null, update = null, fullSize = null, openInBrowser = null, controlsRef, actions = null, className }) {
  const { t } = useI18n();
  return (
    <header className={cn(NAVBAR_ROW_CLASS, "border-border bg-background text-foreground", className)} data-viewer-navbar="">
      <nav aria-label={t("navbar.viewer")} className="flex min-w-0 flex-1 items-center overflow-hidden text-sm">
        {onHome || menu ? <LogoMenu onHome={onHome} menu={menu} /> : null}
        {history ? <HistoryButtons viewHistory={history} /> : null}
        {file ? <span className="flex min-w-0 items-center">
          <FileName path={file} name={name} explorer={explorer} />
          {fileMenu ? <FileMenu path={file} {...fileMenu} /> : null}
        </span> : null}
      </nav>
      <div className={NAVBAR_CONTROLS_CLASS}>
        {update}
        {trailing}
        {fullSize}
        {controlsRef ? <div ref={controlsRef} className="contents" data-view-controls="" /> : null}
        {actions}
        {openInBrowser}
      </div>
    </header>
  );
}
