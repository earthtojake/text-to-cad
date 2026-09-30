import { Ellipsis, Folders, Menu } from "lucide-react";

import { Button } from "@text-to-cad/ui/primitives/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuTrigger } from "@text-to-cad/ui/primitives/dropdown-menu";
import { TooltipHint } from "@text-to-cad/ui/primitives/tooltip";
import { cn } from "@text-to-cad/ui/utils";

import mark from "../../assets/logo-c.svg";
import { EntryMenuItems, useEntryMenuFocusGuard } from "./EntryMenu.jsx";
import { entryMenu } from "./entry-menu.js";
import { InlineName } from "./InlineName.jsx";
import { NavbarLinks } from "./NavbarLinks.jsx";

/**
 * The row above a file, and above a host's home: ONE navbar, the same in every app and on every
 * page, so a person finds each control in the same place whatever is open.
 *
 * Left, in this order: the C mark — the way home where there is one to go to (a burger under the
 * pointer), the brand where there is not; the file explorer's toggle, where the host's files can
 * be browsed; and the open file's name with its ⋯ menu, the same menu a row of the explorer has.
 * The name is not a menu of its own, and has no right-click: the ⋯ is the one door.
 *
 * Right: the file's own actions (a renderer's snapshot), the toggles of any panel the file
 * declares, then the host's links — the version, GitHub and Discord (`NavbarLinks.jsx`).
 *
 * Nothing here is drawn for its own sake: a control appears only where it does something.
 */

/**
 * One class for every toggle in the row, so "highlighted while its panel is open" looks the same
 * on all of them and in every app.
 */
export const PANEL_TOGGLE_CLASSES =
  "size-6 text-muted-foreground aria-pressed:bg-accent aria-pressed:text-accent-foreground";

/**
 * One panel's toggle. `active` is the panel being open, not the button being pressed: it is
 * `aria-pressed`, which is what paints it.
 *
 * @param {object} props
 * @param {import("react").ElementType} props.icon
 * @param {string} props.label The accessible name — what pressing it does.
 * @param {boolean} props.active
 * @param {() => void} props.onClick
 * @param {string} [props.id] Written as `data-file-panel`, for the host's tests.
 * @param {string} [props.testId]
 */
export function PanelToggle({ icon: Icon, label, active, onClick, id, testId }) {
  return (
    <TooltipHint content={label.replace(/^(Show|Hide) /, "").replace(/^files$/, "Files")}><Button
      aria-label={label}
      aria-pressed={active}
      className={PANEL_TOGGLE_CLASSES}
      {...(id ? { "data-file-panel": id } : {})}
      {...(testId ? { "data-testid": testId } : {})}
      onClick={onClick}
      size="icon-xs"
      type="button"
      variant="ghost"
    >
      <Icon className="size-3.5" />
    </Button></TooltipHint>
  );
}

/** The C: a button home, which turns into a burger under the pointer; or, with nowhere to go, the brand. */
function HomeMark({ onHome }) {
  if (!onHome) {
    return <img src={mark} alt="CAD" width={20} height={20} className="mx-0.5 size-5 shrink-0 object-contain" data-navbar-home="" />;
  }
  return <TooltipHint content="Home">
    <button type="button" aria-label="Home" onClick={onHome} data-navbar-home=""
      className="group/home relative flex size-6 shrink-0 items-center justify-center rounded-md text-foreground outline-none transition-colors hover:bg-accent focus-visible:ring-2 focus-visible:ring-ring">
      <img src={mark} alt="" width={20} height={20}
        className="size-5 object-contain transition-opacity group-hover/home:opacity-0 group-focus-visible/home:opacity-0" />
      <Menu aria-hidden="true" strokeWidth={1.75}
        className="absolute size-4 opacity-0 transition-opacity group-hover/home:opacity-100 group-focus-visible/home:opacity-100" />
    </button>
  </TooltipHint>;
}

/** The ⋯ after the file's name: the explorer's own menu for that file, opened by a click. */
function FileActions({ entry, capabilities, platform, onAction }) {
  const guard = useEntryMenuFocusGuard(onAction);
  // A host that can do nothing with the file has no ⋯ at all, rather than an empty menu.
  if (entryMenu(entry, platform, capabilities).length === 0) return null;
  return <DropdownMenu modal={false}>
    <DropdownMenuTrigger asChild><TooltipHint content="File actions"><button aria-label="File actions" data-testid="file-actions" type="button"
      className="flex size-6 shrink-0 items-center justify-center rounded-md text-muted-foreground outline-none transition-colors hover:bg-accent hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring data-[state=open]:bg-accent data-[state=open]:text-accent-foreground">
      <Ellipsis className="size-3.5" />
    </button></TooltipHint></DropdownMenuTrigger>
    <DropdownMenuContent align="start" className="w-56" data-entry-menu={entry.path} onCloseAutoFocus={guard.onCloseAutoFocus} sideOffset={6}>
      <EntryMenuItems capabilities={capabilities} entry={entry} onAction={guard.onAction} platform={platform} surface="dropdown" />
    </DropdownMenuContent>
  </DropdownMenu>;
}

/**
 * @typedef {object} NavbarFile
 * @property {string} path Root-relative: the file on screen.
 * @property {ReadonlySet<import("./entry-menu.js").EntryAction>} capabilities
 * @property {import("./entry-menu.js").Platform} platform
 * @property {(action: import("./entry-menu.js").EntryAction, entry: import("./entry-menu.js").MenuEntryTarget) => void} onAction
 * @property {{ commit(name: string): Promise<boolean>, cancel(): void } | null} [renaming]
 *   While the host renames the file: a field over its name.
 */

/**
 * @param {object} props
 * @param {(() => void) | undefined} [props.onHome] The host's home, when the view is not already on it.
 * @param {{ open: boolean, onToggle: () => void } | null} [props.explorer] The explorer's toggle, where there are files to browse.
 * @param {NavbarFile | null} [props.file] The open file, once the host has named it.
 * @param {import("react").ReactNode} [props.status] After the name: the unsaved-changes dot.
 * @param {import("react").ReactNode} [props.trailing] The file's actions and its panels' toggles.
 * @param {import("../../host/types.js").ViewerLinks} [props.links]
 * @param {import("../../host/types.js").ClipboardPort} props.clipboard
 * @param {(error: Error) => void} [props.onError]
 * @param {string} [props.className]
 */
export function ViewerNavbar({ onHome, explorer = null, file = null, status = null, trailing = null, links, clipboard, onError, className }) {
  const name = file ? file.path.split("/").pop() || file.path : "";
  return (
    <header className={cn("flex h-9 shrink-0 items-center gap-2 border-b border-border bg-background px-2 text-foreground", className)} data-viewer-navbar="">
      <nav aria-label="Viewer" className="flex min-w-0 flex-1 items-center gap-1 overflow-hidden text-sm">
        <HomeMark onHome={onHome} />
        {explorer ? <PanelToggle icon={Folders} id="tree" testId="tree-toggle" active={explorer.open}
          label={explorer.open ? "Hide files" : "Show files"} onClick={explorer.onToggle} /> : null}
        {file ? <span className="ml-1 flex min-w-0 items-center gap-1">
          {file.renaming ? <InlineName initial={name} kind="file" label="Rename file" className="max-w-64"
            onCancel={file.renaming.cancel} onCommit={file.renaming.commit} /> : <>
            {/* The name keeps its width longest: it is what the row is about. Its full path, only when it is cut short. */}
            <TooltipHint content={file.path} overflowOnly><span className="min-w-0 truncate px-0.5" data-file-name="">{name}</span></TooltipHint>
            {status}
            <FileActions entry={{ path: file.path, kind: "file", surface: "navbar" }} capabilities={file.capabilities}
              platform={file.platform} onAction={file.onAction} />
          </>}
        </span> : status}
      </nav>
      <div className="flex shrink-0 items-center gap-0.5">
        {trailing}
        {links ? <NavbarLinks links={links} clipboard={clipboard} onError={onError} /> : null}
      </div>
    </header>
  );
}
