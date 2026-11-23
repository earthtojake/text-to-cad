import { useEffect, useId, useRef, useState } from "react";
import { Moon, Sun } from "lucide-react";
import { ToolbarButton } from "@cad/ui/primitives/toolbar-button";
import { useI18n, english } from "@cad/ui/i18n";
import { VIEWPORT_BACKGROUNDS } from "@cad/core/lib/viewportTheme.js";
import { useViewerMobile } from "../../../file-viewer/responsive.js";
import { OrthographicProjectionIcon, PerspectiveProjectionIcon } from "../camera/ProjectionModeIcons.js";
import { SettingsCard } from "../view-settings/SettingsCard.jsx";
import { useStripButtonClass } from "../tools/stripTouch.js";
import { NAVBAR_VIEW_BUTTON_CLASS } from "./NavbarViewControls.jsx";

/**
 * The view's **Display** (`docs/viewer-ux.md`, "The Display card"): how the picture is looked at, one card for every
 * kind of file, opened by the navbar's Display button (the plain cube, left of Preview; with no
 * navbar the strip's last tile but Preview's, or a row of a phone's More). Its rows are the view's groups, in two
 * sections and ONE hairline between them: the camera's (a board's **Side** and **Mode**, then **Projection** where the
 * view has one) and the picture's (**Style**, the display mode or a board's preset, then the **Background** and a 3D
 * view's **Show grid**). A drawing's or a schematic's is its Background alone. **Reset** puts the file's own settings
 * back to what a file opened for the first time gets, never the Background, which is the person's, the same in every
 * file. It stays open while the person works in the view; its X, its button, Escape, another file and Preview close it.
 *
 * A group is `{ id, label, value, options, onChange, data, reset? }` (a choice: `options` `{ value, label, Icon?,
 * disabled? }`, `data` the attribute each option carries) or `{ id, label, value, onChange, toggle: true, reset? }` (a
 * switch). `reset` is the value a file with no saved record gets (none: Reset leaves it alone). What a change counts
 * (`usage/controls.js`) is the group's `onChange`'s.
 */

// The Background's icons, the app menu's Theme's own: the sun and the moon.
const BACKGROUND_ICONS = Object.freeze({ light: Sun, dark: Moon });
// Which section each group stands in: the camera's, then the picture's.
const CAMERA_GROUPS = Object.freeze(["side", "dimension", "projection"]);

/** A 3D view's (or a board's) display modes, as **Style**. `mode`: `{ value, options, onChange }`; `reset`: its default. */
export function displayGroup(mode, t = english, reset = undefined) {
  if (!mode?.options?.length) return null;
  return { id: "display", label: t("display.style"), value: mode.value, data: "data-display-mode-option", reset,
    options: mode.options.map(({ value, label, Icon, disabled }) => ({ value, label: label ?? t(`mode.${value}`), Icon, disabled: disabled === true })),
    onChange: value => { if (value !== mode.value) mode.onChange(value); } };
}

/** The camera's projection: Orthographic (the default) first, then Perspective, each with its icon. */
export function projectionGroup(projection, t = english, reset = undefined) {
  if (!projection) return null;
  const value = projection.value === "perspective" ? "perspective" : "orthographic";
  return { id: "projection", label: t("projection.label"), value, data: "data-display-projection", reset,
    options: [{ value: "orthographic", label: t("projection.orthographic"), Icon: OrthographicProjectionIcon },
      { value: "perspective", label: t("projection.perspective"), Icon: PerspectiveProjectionIcon }],
    onChange: next => { if (next !== value) projection.onChange(next); } };
}

/** The grid, a switch: every display mode draws it. */
export function gridGroup(grid, t = english, reset = undefined) {
  if (!grid) return null;
  return { id: "grid", label: t("display.showGrid"), toggle: true, value: grid.value === true, data: "data-display-grid", reset,
    onChange: value => grid.onChange(value === true) };
}

/** The viewport's Background, the person's, the same in every file: Light or Dark (`@cad/core/lib/viewportTheme.js`). */
export function backgroundGroup(background, t = english, used = null) {
  if (!background) return null;
  return { id: "background", label: t("display.background"), value: background.value, data: "data-display-background",
    options: VIEWPORT_BACKGROUNDS.map(value => ({ value, label: t(`display.background.${value}`), Icon: BACKGROUND_ICONS[value] })),
    onChange: value => { if (value === background.value) return; used?.(`viewport_background_${value}`); background.onChange(value); } };
}

/**
 * A 3D view's groups: Projection, then Style, Background and Show grid. `defaults`: what a file with no saved record
 * gets (`viewerDisplaySettings.js`'s `DISPLAY_DEFAULTS`), Reset's.
 */
export function viewGroups3d({ mode = null, projection = null, grid = null, background = null, defaults = null, t = english, used = null }) {
  return [projectionGroup(projection, t, defaults?.projection), displayGroup(mode, t, defaults?.mode), backgroundGroup(background, t, used),
    gridGroup(grid, t, defaults?.grid)].filter(Boolean);
}

/** What each group has on screen, said on Display's button (`data-view-display="solid"`, `data-view-side="top"` …), to a host or a test. */
function groupStates(groups) {
  return Object.fromEntries(groups.map(group => [`data-view-${group.id}`, String(group.value)]));
}

/**
 * Display's icon, the plain cube, on every file and whatever is on screen; Preview's bar's settings toggle wears the
 * same one (`usePreviewFrame.jsx`): how the picture is looked at, in Preview as outside it.
 */
export const DisplayIcon = OrthographicProjectionIcon;

/** Whether Reset has something to put back: a group of the file's own away from its default. */
export const displayChanged = groups => groups.some(group => group.reset !== undefined && group.value !== group.reset);

/** The card's rows: the camera's section, then the picture's (`SettingsCard.jsx`'s rows). */
export function displaySections(groups) {
  const row = group => (group.toggle
    ? { kind: "switch", id: group.id, label: group.label, value: group.value, onChange: group.onChange, controlProps: { [group.data]: "" } }
    : { kind: "select", id: group.id, label: group.label, value: group.value, options: group.options, onChange: group.onChange, data: group.data });
  return [groups.filter(group => CAMERA_GROUPS.includes(group.id)).map(row), groups.filter(group => !CAMERA_GROUPS.includes(group.id)).map(row)];
}

// The strip's tile: the strip's own size, its tooltip over it.
function DisplayTile(props) {
  return <ToolbarButton {...props} className={useStripButtonClass()} tooltipSide="top" />;
}

/**
 * Display's button and its card, for a frame (`RendererShell.jsx`, `FlatViewFrame.jsx`): `navbarButton`, the navbar's;
 * `stripView`, the strip's tile and a phone's More row where there is no navbar; `card`, what the frame docks at the
 * view's right edge (`ViewFrame.jsx`'s `card`: `{ open, content }`). The button is a toggle (pressed while the card is
 * open). `closeKey`: another value (another file) closes it; `closed`: it is closed while true (Preview).
 * @param {{ groups: object[], onReset?: (() => void) | null, disabled?: boolean, closeKey?: unknown, closed?: boolean }} options
 */
export function useDisplaySettings({ groups, onReset = null, disabled = false, closeKey = null, closed = false }) {
  const { t } = useI18n();
  const mobile = useViewerMobile();
  const id = useId();
  const [open, setOpen] = useState(false);
  const [key, setKey] = useState(closeKey);
  if (key !== closeKey) { setKey(closeKey); if (open) setOpen(false); }
  else if (open && (closed || !groups.length)) setOpen(false);
  const buttonRef = useRef(null);
  const cardRef = useRef(null);
  // Closing hands the keyboard, where it was in the card, back to the button.
  const close = () => {
    const focused = typeof document === "undefined" ? null : document.activeElement;
    if (focused && cardRef.current?.contains(focused)) buttonRef.current?.focus({ preventScroll: true });
    setOpen(false);
  };
  const toggle = () => { if (open) close(); else setOpen(true); };
  const Icon = DisplayIcon;
  const label = t("display.label");
  const shown = open && !closed;
  // On a phone the card is a popover: a press anywhere else (the model, the navbar) puts it away, as the phone's sheet
  // goes. Its button keeps its own toggle, and what the card opened (a dropdown's list, portalled out of it) is the card's.
  // On a desktop it stays while the person works the view, and closes by its X, its button or Escape.
  const closeRef = useRef(close);
  closeRef.current = close;
  useEffect(() => {
    if (!mobile || !shown || typeof document === "undefined") return undefined;
    const away = event => {
      const target = event.target;
      if (!(target instanceof Element)) return;
      if (cardRef.current?.contains(target) || buttonRef.current?.contains(target)) return;
      if (target.closest("[data-radix-popper-content-wrapper], [role=menu], [role=listbox], [role=dialog]")) return;
      closeRef.current();
    };
    document.addEventListener("pointerdown", away, true);
    return () => document.removeEventListener("pointerdown", away, true);
  }, [mobile, shown]);
  // Escape on the button, as in the card, puts the card away.
  const onKeyDown = event => { if (event.key === "Escape" && shown && !event.defaultPrevented) { event.preventDefault(); close(); } };
  const buttonProps = { ref: buttonRef, label, disabled, onClick: toggle, onKeyDown, "aria-pressed": shown, "aria-expanded": shown,
    "aria-controls": shown ? id : undefined, "data-escape-owner": shown ? "" : undefined, "data-display-settings": "", ...groupStates(groups) };
  return {
    open: shown, close,
    navbarButton: groups.length ? <ToolbarButton {...buttonProps} tooltipSide="bottom" tooltip={!mobile} className={NAVBAR_VIEW_BUTTON_CLASS}>
      <Icon aria-hidden="true" />
    </ToolbarButton> : null,
    stripView: groups.length ? { id: "display", label, icon: <Icon aria-hidden="true" />, disabled, active: shown, onSelect: toggle,
      tile: <DisplayTile {...buttonProps}><Icon aria-hidden="true" /></DisplayTile> } : null,
    card: { open: shown, content: <SettingsCard ref={cardRef} id={id} title={label} closeLabel={t("display.close")} onClose={close} closeOnEscape
      sections={displaySections(groups)} data-display-settings-card=""
      {...(groups.some(group => group.reset !== undefined) ? { onReset, resetLabel: t("settings.reset"), resetDisabled: !displayChanged(groups),
        resetProps: { "data-display-reset": "" } } : {})} /> }
  };
}
