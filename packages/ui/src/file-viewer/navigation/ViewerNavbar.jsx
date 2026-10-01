import { ArrowLeft, Ellipsis, Folders } from "lucide-react";

import { Button } from "@text-to-cad/ui/primitives/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuTrigger } from "@text-to-cad/ui/primitives/dropdown-menu";
import { TooltipHint } from "@text-to-cad/ui/primitives/tooltip";
import { cn } from "@text-to-cad/ui/utils";

import { EntryMenuItems, useEntryMenuFocusGuard } from "./EntryMenu.jsx";
import { entryMenu } from "./entry-menu.js";
import { InlineName } from "./InlineName.jsx";
import { NavbarLinks } from "./NavbarLinks.jsx";

/**
 * The row above a file: ONE navbar, the same in every app, so a person finds each control in the
 * same place whatever is open. A host's home has none; it holds the links itself.
 *
 * Left, in this order: the way back to the host's home, where there is one; the file explorer's
 * toggle, where the host's files can be browsed; and the open file's name with its ⋯ menu, the
 * same menu a row of the explorer has — or, with no file open, the words "Select file", which
 * are not a control: the explorer's toggle beside them is. The name is not a menu of its own, and
 * has no right-click: the ⋯ is the one door.
 *
 * Right: the file's own actions, the toggles of any panel the file declares, the host's version,
 * whose menu holds GitHub and Discord (`NavbarLinks.jsx`), then the renderer's view controls
 * (`controlsRef`: the CAD viewer's Display settings and Preview).
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

/** Back to the host's home, from a file: an arrow the size of the row's other icon buttons. */
function BackButton({ onBack }) {
  return <TooltipHint content="Back"><Button type="button" variant="ghost" size="icon-xs" aria-label="Back" onClick={onBack}
    className="size-6 text-muted-foreground hover:text-foreground" data-navbar-back="">
    <ArrowLeft className="size-3.5" />
  </Button></TooltipHint>;
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
 * @param {(() => void) | undefined} [props.onBack] Back to the host's home, from a file.
 * @param {{ open: boolean, onToggle: () => void } | null} [props.explorer] The explorer's toggle, where there are files to browse.
 * @param {NavbarFile | null} [props.file] The open file, once the host has named it.
 * @param {boolean} [props.selecting] No file is open: the name's place asks for one.
 * @param {import("react").ReactNode} [props.status] After the name: the unsaved-changes dot.
 * @param {import("react").ReactNode} [props.trailing] The file's actions and its panels' toggles.
 * @param {(element: HTMLDivElement | null) => void} [props.controlsRef] The box the renderer draws its view controls into.
 * @param {import("../../host/types.js").ViewerLinks} [props.links]
 * @param {import("../../host/types.js").ClipboardPort} props.clipboard
 * @param {(error: Error) => void} [props.onError]
 * @param {string} [props.className]
 */
export function ViewerNavbar({ onBack, explorer = null, file = null, selecting = false, status = null, trailing = null, controlsRef, links, clipboard, onError, className }) {
  const name = file ? file.path.split("/").pop() || file.path : "";
  return (
    <header className={cn("flex h-9 shrink-0 items-center gap-2 border-b border-border bg-background px-2 text-foreground", className)} data-viewer-navbar="">
      <nav aria-label="Viewer" className="flex min-w-0 flex-1 items-center gap-1 overflow-hidden text-sm">
        {onBack ? <BackButton onBack={onBack} /> : null}
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
        </span> : selecting && explorer ? <span className="ml-1 truncate px-0.5 text-muted-foreground" data-select-file="">Select file</span> : status}
      </nav>
      <div className="flex shrink-0 items-center gap-0.5">
        {trailing}
        {links ? <NavbarLinks links={links} clipboard={clipboard} onError={onError} /> : null}
        <div ref={controlsRef} className="contents" data-navbar-controls="" />
      </div>
    </header>
  );
}
