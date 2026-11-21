import { useRef, useState } from "react";
import { ChevronDown, Moon, SlidersHorizontal, Sun } from "lucide-react";
import {
  DropdownMenu, DropdownMenuCheckboxItem, DropdownMenuContent, DropdownMenuItem, DropdownMenuRadioGroup,
  DropdownMenuRadioItem, DropdownMenuSeparator, DropdownMenuShortcut, DropdownMenuSub, DropdownMenuSubContent,
  DropdownMenuSubTrigger, DropdownMenuTrigger
} from "@cad/ui/primitives/dropdown-menu";
import { ToolbarButton } from "@cad/ui/primitives/toolbar-button";
import { useI18n, english } from "@cad/ui/i18n";
import { useViewerMobile } from "../../../file-viewer/responsive.js";
import { cn } from "@cad/ui/utils";
import { VIEWPORT_BACKGROUNDS } from "@cad/core/lib/viewportTheme.js";
import { FLOATING_SURFACE_CLASS } from "../../../lib/floatingSurface.js";
import { OrthographicProjectionIcon, PerspectiveProjectionIcon } from "../camera/ProjectionModeIcons.js";
import { NAVBAR_VIEW_BUTTON_CLASS } from "./NavbarViewControls.jsx";

/**
 * The view's settings (`settings-ui.md`, "The View menu"): how the picture is looked at, in groups — a 3D view's
 * **Display** (its modes), **Projection**, **Background** and **Grid**; a board's **Side**, **Mode** (2D/3D), its
 * **Display** presets (and in 3D Projection) and Background; a drawing's Background. They are **View** (`ViewMenu`):
 * a 3D view's tile in the row under its cube, a flat view's navbar **View ▾**, ONE stock DropdownMenu on a desktop and
 * on a phone alike: a choice is a submenu, its row the group's name and, muted at its right, the choice's name (no
 * icon); a switch (Grid) a check row.
 *
 * A group is `{ id, label, value, options, onChange }` (a choice: `options` `{ value, label, Icon?, disabled?,
 * shortcut? }`, one `data` attribute name for its items) or `{ id, label, value, onChange, toggle: true }` (a
 * switch). What a change counts (`usage/controls.js`) is the group's `onChange`'s, so a control is counted under the
 * same name its buttons were.
 */

// The Background's icons, the app menu's Theme's own: the sun and the moon.
const BACKGROUND_ICONS = Object.freeze({ light: Sun, dark: Moon });

/** A 3D view's (or a board's) display modes. `mode`: `{ value, options, onChange }` (`DisplayPopover`'s). */
export function displayGroup(mode, t = english) {
  if (!mode?.options?.length) return null;
  return { id: "display", label: t("display.label"), value: mode.value, data: "data-display-mode-option",
    options: mode.options.map(({ value, label, Icon, disabled }) => ({ value, label: label ?? t(`mode.${value}`), Icon, disabled: disabled === true })),
    onChange: value => { if (value !== mode.value) mode.onChange(value); } };
}

/** The camera's projection: Perspective, then Orthographic, each with its icon. */
export function projectionGroup(projection, t = english) {
  if (!projection) return null;
  const value = projection.value === "perspective" ? "perspective" : "orthographic";
  return { id: "projection", label: t("projection.label"), value, data: "data-display-projection",
    options: [{ value: "perspective", label: t("projection.perspective"), Icon: PerspectiveProjectionIcon },
      { value: "orthographic", label: t("projection.orthographic"), Icon: OrthographicProjectionIcon }],
    onChange: next => { if (next !== value) projection.onChange(next); } };
}

/** The grid, a switch: every display mode draws it. */
export function gridGroup(grid, t = english) {
  if (!grid) return null;
  return { id: "grid", label: t("display.grid"), toggle: true, value: grid.value === true, data: "data-display-grid",
    onChange: value => grid.onChange(value === true) };
}

/** The viewport's Background, the person's, the same in every file: Light or Dark (`@cad/core/lib/viewportTheme.js`). */
export function backgroundGroup(background, t = english, used = null) {
  if (!background) return null;
  return { id: "background", label: t("display.background"), value: background.value, data: "data-display-background",
    options: VIEWPORT_BACKGROUNDS.map(value => ({ value, label: t(`display.background.${value}`), Icon: BACKGROUND_ICONS[value] })),
    onChange: value => { if (value === background.value) return; used?.(`viewport_background_${value}`); background.onChange(value); } };
}

/** A 3D view's groups, top to bottom: Display, Projection, Background, Grid. */
export function viewGroups3d({ mode = null, projection = null, grid = null, background = null, t = english, used = null }) {
  // Projection first: the setting a 3D view's is changed most (the owner's call), and the one its tile wears.
  return [projectionGroup(projection, t), displayGroup(mode, t), backgroundGroup(background, t, used), gridGroup(grid, t)].filter(Boolean);
}

/** What each group has on screen, said on View's button (`data-view-display="solid"`, `data-view-side="top"` …), to a host or a test. */
function groupStates(groups) {
  return Object.fromEntries(groups.map(group => [`data-view-${group.id}`, String(group.value)]));
}

/**
 * The trigger's icon: a corner tile's (a 3D view's), the projection on screen's (`by: "projection"`), the setting it
 * changes most; the navbar's View ▾, the display mode on screen's; else the view's settings' own (the sliders).
 */
function currentIcon(groups, by = "display") {
  const group = groups.find(entry => entry.id === by) || groups.find(entry => entry.id === "display");
  return group?.options.find(option => option.value === group.value)?.Icon || SlidersHorizontal;
}

// Where a submenu stands: beside its row, on the side with room (the left, near the screen's right edge, where View
// is). On a phone the menu stands against the screen's right edge, so the room at its left is as wide as it can be,
// and a submenu overlaps its parent's icon column by this much, so its rows stay whole and on the screen.
const PHONE_SUB_OVERLAP = 16;
// The gap kept between a menu and the screen's edge.
const EDGE_PX = 8;

/**
 * A choice's submenu: its row (the group's name at the left; at the right the choice on screen's name, muted, and the
 * chevron; no icon), its options (each with its icon, the one on screen ticked).
 */
function ViewChoice({ group, mobile, boundary }) {
  const current = group.options.find(option => option.value === group.value);
  return <DropdownMenuSub>
    <DropdownMenuSubTrigger data-view-sub={group.id}>
      <span className="flex-1">{group.label}</span>
      <span className="truncate text-muted-foreground" data-view-sub-value="">{current?.label ?? ""}</span>
    </DropdownMenuSubTrigger>
    <DropdownMenuSubContent sideOffset={mobile ? -PHONE_SUB_OVERLAP : 2} alignOffset={-5} collisionPadding={8}
      collisionBoundary={boundary || undefined} aria-label={group.label} data-view-sub-content={group.id}
      className={cn(FLOATING_SURFACE_CLASS, mobile ? "min-w-36" : "min-w-40", "max-w-(--radix-dropdown-menu-content-available-width) data-[state=closed]:animate-none!")}>
      <DropdownMenuRadioGroup aria-label={group.label} value={group.value} onValueChange={group.onChange}>
        {group.options.map(({ value, label, Icon: OptionIcon, disabled: off, shortcut }) => <DropdownMenuRadioItem key={value} value={value}
          disabled={off === true} {...{ [group.data]: value }}>
          {OptionIcon ? <OptionIcon className="size-4" /> : <span className="size-4 shrink-0" aria-hidden="true" />}{label}
          {shortcut ? <DropdownMenuShortcut className="mr-4">{shortcut}</DropdownMenuShortcut> : null}
        </DropdownMenuRadioItem>)}
      </DropdownMenuRadioGroup>
    </DropdownMenuSubContent>
  </DropdownMenuSub>;
}

/**
 * **View**: how the picture is looked at, one stock DropdownMenu on a desktop and on a phone alike. A 3D view's is a
 * tile of the cube's row (`tile: "corner"`, `ViewCornerStack.jsx`'s `CubeRow`: Home's 24px, the projection on
 * screen's icon, no chevron), its menu under the row (`placement`); a phone's the corner's 36px tile alone (`tile:
 * "phone"`), with the same icon. A 3D view's rows: Projection ▸ first, then Display ▸, Background ▸ and Grid. A flat view's is still the navbar's **View ▾** (`NavbarViewControls.jsx`: its icon — a board's preset's,
 * the sliders where the view has no modes — and a chevron). Each choice is a submenu (Display ▸, Projection ▸,
 * Background ▸; a board's Side ▸ and Mode ▸), its row the group's name with, muted at its right, the choice's name and
 * the chevron — no icon on the menu's own rows; its submenu the options, each with its icon, the one on screen ticked.
 * Grid is a check row of the menu itself (its name, the tick at the right while on), which leaves the menu open. On a
 * phone, which has no cube, **Reset view** (`onReset`: a 3D view's Home, a drawing's fit, a board's 3D Home) ends it. A
 * choice closes the menu. A submenu opens on hover or a press (a tap, on a phone), to the side with room.
 * @param {{ groups: object[], onReset?: (() => void) | null, disabled?: boolean, boundary?: HTMLElement | null,
 *   onOpenChange?: (open: boolean) => void, tile?: "corner" | "phone" | null, className?: string | null,
 *   placement?: { align: "start" | "end", alignOffset: number } | null }} props
 */
export function ViewMenu({ groups, onReset = null, disabled = false, boundary = null, onOpenChange, tile = null, className = null, placement = null }) {
  const { t } = useI18n();
  const mobile = useViewerMobile();
  const reset = mobile && onReset ? onReset : null;
  // A phone's navbar menu ends at the screen's right edge, past View's own end (Preview stands at its right), so its
  // submenus have the room at its left: how far, read as it opens. A corner tile stands at that edge already.
  const trigger = useRef(null);
  const [toEdge, setToEdge] = useState(0);
  const openChange = open => {
    if (open && mobile && !tile && trigger.current && typeof window !== "undefined") {
      setToEdge(Math.max(0, window.innerWidth - EDGE_PX - trigger.current.getBoundingClientRect().right));
    }
    onOpenChange?.(open);
  };
  if (!groups.length && !reset) return null;
  const Icon = currentIcon(groups, tile ? "projection" : "display");
  const display = groups.find(group => group.id === "display");
  const choices = groups.filter(group => !group.toggle), toggles = groups.filter(group => group.toggle);
  return <DropdownMenu modal={false} onOpenChange={openChange}>
    <DropdownMenuTrigger asChild>
      <ToolbarButton ref={trigger} label={t("view.menu")} tooltipSide="bottom" tooltip={!mobile} disabled={disabled}
        className={tile ? cn(className, tile === "phone" && "size-9 [&>svg]:size-5!") : cn(NAVBAR_VIEW_BUTTON_CLASS, "w-auto gap-0.5 px-1.5")}
        data-view-menu="" data-display-mode={display?.value} {...groupStates(groups)}>
        <Icon aria-hidden="true" />
        {tile ? null : <ChevronDown className="size-3! opacity-60" aria-hidden="true" />}
      </ToolbarButton>
    </DropdownMenuTrigger>
    {/* Closes with no exit animation, so a quick second press always reaches the button. */}
    <DropdownMenuContent side="bottom" align={placement?.align ?? "end"} sideOffset={6} alignOffset={placement ? placement.alignOffset : mobile && !tile ? -toEdge : 0} collisionPadding={EDGE_PX} collisionBoundary={boundary || undefined} aria-label={t("view.menu")}
      className={cn(FLOATING_SURFACE_CLASS, "min-w-52 data-[state=closed]:animate-none!")} data-view-menu-content="">
      {choices.map(group => <ViewChoice key={group.id} group={group} mobile={mobile} boundary={boundary} />)}
      {toggles.length && choices.length ? <DropdownMenuSeparator /> : null}
      {/* A switch leaves the menu open, as every checkbox row in a menu does: the grid is seen coming and going. */}
      {toggles.map(group => <DropdownMenuCheckboxItem key={group.id} checked={group.value} onCheckedChange={value => group.onChange(value === true)}
        onSelect={event => event.preventDefault()} data-view-toggle={group.id} {...{ [group.data]: "" }}>
        {group.label}
      </DropdownMenuCheckboxItem>)}
      {reset ? <>
        {groups.length ? <DropdownMenuSeparator /> : null}
        <DropdownMenuItem onSelect={reset} data-view-reset="">{t("view.reset")}</DropdownMenuItem>
      </> : null}
    </DropdownMenuContent>
  </DropdownMenu>;
}
