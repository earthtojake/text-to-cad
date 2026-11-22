import { Fragment, useLayoutEffect, useRef, useState } from "react";
import { Ellipsis } from "lucide-react";
import {
  DropdownMenu, DropdownMenuCheckboxItem, DropdownMenuContent, DropdownMenuInlineSub, DropdownMenuInlineSubContent,
  DropdownMenuInlineSubTrigger, DropdownMenuItem, DropdownMenuTrigger
} from "@cad/ui/primitives/dropdown-menu";
import { ToolbarButton } from "@cad/ui/primitives/toolbar-button";
import { cn } from "@cad/ui/utils";
import { PHONE_SCALE } from "../../../lib/scale.js";
import { FLOATING_CHROME_SURFACE_CLASS, FLOATING_SURFACE_CLASS } from "../../../lib/floatingSurface.js";
import { STRIP_SHAPE_CLASS, StripTouchProvider, TOP_STRIP_BUTTON_CLASS, TOP_STRIP_SHAPE_CLASS, TOUCH_STRIP_BUTTON_CLASS } from "./stripTouch.js";
import { ChangedDot } from "./ChangedDot.jsx";
import { useI18n } from "@cad/ui/i18n";

export { STRIP_BUTTON_CLASS, StripTouchProvider, TOP_STRIP_BUTTON_CLASS, TOUCH_STRIP_BUTTON_CLASS, useStripButtonClass, useStripTouch } from "./stripTouch.js";

/**
 * One tool of the strip. The strip draws it; whoever hands it over decides what
 * it is, when it exists and what pressing it does. A tool with settings (Select's filter,
 * Measure's) has a small chevron right after its button that opens them (`menu`, a
 * `ToolSettingsMenu` with its "chevron" trigger), as a design tool's toolbar has it.
 *
 * @typedef {object} ViewportTool
 * @property {string} id
 * @property {string} label  The button's accessible name and tooltip.
 * @property {string} [tooltip]  Its tooltip where it says more than its name (a drawing tool's, what it draws with now).
 * @property {string} [shortcut]  Its key (`toolShortcuts.js`), shown after the name in its tooltip.
 * @property {import("react").ReactNode} icon
 * @property {boolean} [active]
 * @property {boolean} [disabled]
 * @property {() => void} [onSelect]  Every press of the button.
 * @property {string} [description]  `aria-description`.
 * @property {import("react").ReactNode} [menu]  Its modes: the chevron after its button, and the menu it opens.
 * @property {boolean} [changed]  What it sets is off its default (an effect on the model, its tool not in hand): a dot in
 *   its tile's corner.
 * @property {string} [group]  The strip's group it is in (the tools that pick or draw — Select, Draw, Measure — then
 *   the model's effects, "model"): their order, never a rule, since the strip draws none.
 */

/**
 * One of the view's controls at the strip's end, where no navbar holds them (Display, Preview; a phone's zoom, in More):
 * its tile as drawn on the
 * strip (`tile`), and what it is as a row of the touch strip's More menu, when there is no room for
 * it: `onSelect` for a press, or `popover` for a control whose tile opens a popover, which then
 * opens from More itself (`anchor`, the More button's ref).
 *
 * @typedef {object} ViewportViewControl
 * @property {string} id
 * @property {string} label
 * @property {import("react").ReactNode} icon
 * @property {boolean} [disabled]
 * @property {boolean} [active]  A control that stays on (a phone's view control): a ticked row in More.
 * @property {import("react").ReactNode} tile
 * @property {() => void} [onSelect]
 * @property {(props: { anchor: import("react").RefObject<HTMLElement>, open: boolean, onOpenChange(open: boolean): void }) => import("react").ReactNode} [popover]
 * @property {(props: { openPopover(): void }) => import("react").ReactNode} [submenu]  In More, its choices (the zoom's),
 *   opened under its row in More itself, as a phone's menus open a submenu (`DropdownMenuInlineSub`: there is no room
 *   beside More for one); `openPopover` opens its `popover` from More.
 */

// A tool with a menu is ONE control (Select, Measure): its button, then its menu's small chevron
// (`ToolSettingsMenu`'s "chevron" trigger), touching, under one rounded fill. The fill lights the pair
// on hover, while the tool is in hand and while its menu is open; the chevron's half only brightens,
// on its own hover and while its menu is open (`CHEVRON_CLASS`), with no line between them, so the two never
// read as two buttons side by side.
// A tool with a menu is one fill round its button and chevron: the wrapper's, in the toolbar's fills (the dark's the
// foreground over the surface, as `TOOLBAR_ICON_BUTTON_CLASS`'s), its button's own put away in both themes.
const SPLIT_CLASS = ["group/split inline-flex items-center rounded-control transition hover:bg-sidebar-accent data-[active]:bg-sidebar-accent has-[[aria-expanded=true]]:bg-sidebar-accent",
  "dark:hover:bg-foreground/10 dark:data-[active]:bg-foreground/16 dark:has-[[aria-expanded=true]]:bg-foreground/16"].join(" ");
const SPLIT_BUTTON_CLASS = ["rounded-r-none hover:bg-transparent data-[variant=secondary]:bg-transparent data-[variant=secondary]:hover:bg-transparent group-hover/split:text-sidebar-accent-foreground",
  "dark:hover:bg-transparent dark:data-[variant=secondary]:bg-transparent dark:data-[variant=secondary]:hover:bg-transparent"].join(" ");

// A plain function, not a component: the strip's own output is the buttons.
function toolButton(tool, className = TOP_STRIP_BUTTON_CLASS, touch = false) {
  const active = tool.active === true;
  const button = <ToolbarButton tooltipSide="top" label={tool.label} tooltip={tool.tooltip ?? true} shortcut={tool.shortcut} active={active} disabled={tool.disabled}
    className={cn(className, tool.changed && "relative", tool.menu && SPLIT_BUTTON_CLASS)} aria-pressed={active} aria-description={tool.description} onClick={() => tool.onSelect()}
    data-changed={tool.changed ? "" : undefined}>
    {tool.icon}
    {tool.changed ? <ChangedDot /> : null}
  </ToolbarButton>;
  if (!tool.menu) return button;
  return <span className={SPLIT_CLASS} data-tool-split="" data-active={active ? "" : undefined}>{button}{tool.menu}</span>;
}

// The strip: Figma's toolbar's proportions on a desktop (40px, `TOP_STRIP_SHAPE_CLASS`), the touch strip's on a phone.
const GROUP_CLASS = `pointer-events-auto inline-flex max-w-full ${FLOATING_CHROME_SURFACE_CLASS}`;
// A More row's icon at a menu item's standard size (16px) and one line weight, whatever drew it
// (a tool's own glyph, a view control's), so the rows read as one list.
const MORE_ICON_CLASS = "flex size-4 shrink-0 items-center justify-center [&_svg]:size-4! [&_:is(svg,path,circle,line,polyline,polygon,rect,ellipse)]:[stroke-width:2px]";


/**
 * The interaction tools: a dumb strip positioned by the viewport shell. It renders the
 * tools it is handed, left to right, then the view's own controls where no navbar holds them (`views`: Display, then
 * Preview where the view has it), which are no tools: pressing one leaves the tool in hand as it is. No rule parts
 * them; the strip is one row of tiles at Figma's toolbar's proportions (a 40px bar, 28px tiles). It holds no state and knows no tool by name. On a phone (`touch`) it is one row of
 * touch-sized tiles, the tools, with the view's controls (and any tool that does not fit) in a More
 * menu (`TouchStrip`).
 *
 * @param {{ tools: ViewportTool[], views?: ViewportViewControl[], touch?: boolean }} props
 */
export default function FloatingToolBar({ tools = [], views = [], touch = false }) {
  // Nothing to hold, no strip: an empty bar is never drawn.
  const { t } = useI18n();
  if (!tools.length && !views.length) return null;
  if (touch) return <TouchStrip tools={tools} views={views} />;
  return (<div className="relative z-20 flex max-w-full shrink-0 flex-col items-end gap-1" data-cad-toolbar="tools">
      <div role="group" aria-label={t("toolbar.tools")} className={cn(GROUP_CLASS, TOP_STRIP_SHAPE_CLASS, "flex-wrap")}>
        {tools.map(tool => <Fragment key={tool.id}>{toolButton(tool)}</Fragment>)}
        {views.length ? <span className="inline-flex items-center gap-1" data-view-controls="">
          {views.map(view => <Fragment key={view.id}>{view.tile}</Fragment>)}
        </span> : null}
      </div>
  </div>);
}

// The touch strip's geometry, as its classes draw it at a phone's scale (`lib/scale.js`): its tiles the control,
// the step apart, a tool's chevron half a tile and touching its button, and 5px of padding inside a 1px border.
const TILE_PX = PHONE_SCALE.control, CHEVRON_PX = PHONE_SCALE.control / 2, GAP_PX = PHONE_SCALE.step, FRAME_PX = 12;

/**
 * How many of the strip's entries (its tools, then its view controls) fit, in order, in `room`
 * pixels: all of them, or as many as leave room for the More button that holds the rest.
 * @param {{ width: number, view: boolean }[]} entries
 */
export function touchStripFit(entries, room, { more = false } = {}) {
  const width = (count, more) => {
    const shown = entries.slice(0, count);
    const items = shown.length + (more ? 1 : 0);
    return FRAME_PX + shown.reduce((sum, entry) => sum + entry.width, 0) + (more ? TILE_PX : 0)
      + Math.max(0, items - 1) * GAP_PX;
  };
  if (!more && width(entries.length, false) <= room) return entries.length;
  if (more && width(entries.length, true) <= room) return entries.length;
  let count = entries.length - 1;
  while (count > 0 && width(count, true) > room) count -= 1;
  return count;
}

/**
 * A phone's strip: one row of 36px tiles across the view, its tools; the view's controls are always
 * the rows of a More menu (an ellipsis, last on the strip), with any tools that do not fit, from the
 * end, before them. A tool there is a checkbox row, ticked while it is in hand; a view control is
 * its press, or its popover, which then opens from More.
 */
function TouchStrip({ tools, views }) {
  const { t } = useI18n();
  const root = useRef(null);
  const more = useRef(null);
  const [room, setRoom] = useState(Infinity);
  const [openView, setOpenView] = useState(null);
  const pending = useRef(null);
  useLayoutEffect(() => {
    // The room is the column the strip is centred in, which spans the view within its inset.
    const column = root.current?.closest("[data-cad-tool-groups]") || root.current?.parentElement;
    if (!column) return undefined;
    const measure = () => setRoom(column.clientWidth || Infinity);
    measure();
    if (typeof ResizeObserver === "undefined") return undefined;
    const observer = new ResizeObserver(measure);
    observer.observe(column);
    return () => observer.disconnect();
  }, []);
  // The view's controls are always More's rows on a phone, never tiles: the strip keeps to the
  // tools, and what of them does not fit joins the controls in More.
  const toolEntries = tools.map(tool => ({ tool, view: false, width: TILE_PX + (tool.menu ? CHEVRON_PX : 0) }));
  const viewEntries = views.map(view => ({ control: view, view: true, width: TILE_PX }));
  const count = touchStripFit(toolEntries, room, { more: viewEntries.length > 0 });
  const shown = toolEntries.slice(0, count), hidden = [...toolEntries.slice(count), ...viewEntries];
  const shownTools = shown.filter(entry => !entry.view), shownViews = shown.filter(entry => entry.view);
  // What opens a popover from More: a view control's.
  const overflowPopovers = hidden.filter(entry => entry.view).map(entry => entry.control).filter(item => item.popover);
  const popoverView = overflowPopovers.find(item => item.id === openView);
  // A tool in hand that lives in More: More's button is drawn selected while it is (its row checked).
  const heldInMore = hidden.some(entry => !entry.view && entry.tool.active === true);
  return <StripTouchProvider value={true}>
    <div ref={root} className="relative z-20 flex max-w-full shrink-0 flex-col items-end gap-1" data-cad-toolbar="tools" data-touch-strip="">
      <div role="group" aria-label={t("toolbar.tools")} className={cn(GROUP_CLASS, TOP_STRIP_SHAPE_CLASS, "flex-nowrap")}>
        {shownTools.map(({ tool }) => <Fragment key={tool.id}>{toolButton(tool, TOUCH_STRIP_BUTTON_CLASS, true)}</Fragment>)}
        {shownViews.length ? <span className="inline-flex items-center gap-1" data-view-controls="">
          {shownViews.map(({ control }) => <Fragment key={control.id}>{control.tile}</Fragment>)}
        </span> : null}
        {hidden.length ? <DropdownMenu modal={false}>
          <DropdownMenuTrigger asChild>
            <ToolbarButton ref={more} tooltipSide="top" label={t("toolbar.more")} active={heldInMore} className={TOUCH_STRIP_BUTTON_CLASS} data-strip-more="">
              <Ellipsis aria-hidden="true" />
            </ToolbarButton>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" sideOffset={6} collisionPadding={8} aria-label={t("toolbar.more")}
            className={cn(FLOATING_SURFACE_CLASS, "data-[state=closed]:animate-none!")}
            onCloseAutoFocus={event => {
              // A popover chosen here opens from More once the menu is gone, keeping the focus.
              if (!pending.current) return;
              event.preventDefault();
              setOpenView(pending.current);
              pending.current = null;
            }}>
            {hidden.map(entry => entry.view
              ? entry.control.submenu
                // A phone has no room beside More for a submenu: its choices open under its row, in More itself.
                ? <DropdownMenuInlineSub key={entry.control.id}>
                  <DropdownMenuInlineSubTrigger disabled={entry.control.disabled}>
                    <span className={MORE_ICON_CLASS} aria-hidden="true">{entry.control.icon}</span>{entry.control.label}
                  </DropdownMenuInlineSubTrigger>
                  <DropdownMenuInlineSubContent aria-label={entry.control.label}>
                    {entry.control.submenu({ openPopover: () => { pending.current = entry.control.id; } })}
                  </DropdownMenuInlineSubContent>
                </DropdownMenuInlineSub>
              : entry.control.active !== undefined
                ? <DropdownMenuCheckboxItem key={entry.control.id} checked={entry.control.active === true} disabled={entry.control.disabled}
                  onSelect={() => entry.control.onSelect?.()}>
                  <span className={MORE_ICON_CLASS} aria-hidden="true">{entry.control.icon}</span>{entry.control.label}
                </DropdownMenuCheckboxItem>
                : <DropdownMenuItem key={entry.control.id} disabled={entry.control.disabled}
                onSelect={() => { if (entry.control.popover) pending.current = entry.control.id; else entry.control.onSelect?.(); }}>
                <span className={MORE_ICON_CLASS} aria-hidden="true">{entry.control.icon}</span>{entry.control.label}
              </DropdownMenuItem>
              : <DropdownMenuCheckboxItem key={entry.tool.id} checked={entry.tool.active === true} disabled={entry.tool.disabled}
                onSelect={() => entry.tool.onSelect()}>
                <span className={MORE_ICON_CLASS} aria-hidden="true">{entry.tool.icon}</span>{entry.tool.label}
              </DropdownMenuCheckboxItem>)}
          </DropdownMenuContent>
        </DropdownMenu> : null}
        {popoverView ? popoverView.popover({ anchor: more, open: true, onOpenChange: open => { if (!open) setOpenView(null); } }) : null}
      </div>
    </div>
  </StripTouchProvider>;
}
