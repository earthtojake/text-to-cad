import { TooltipHint } from "@text-to-cad/ui/primitives/tooltip";
import { Children, useEffect, useId, useRef, useState } from "react";
import { Minus, Plus } from "lucide-react";
import { cn } from "@text-to-cad/ui/utils";
import { Button } from "@text-to-cad/ui/primitives/button";
import { ColorPicker } from "@text-to-cad/ui/primitives/color-picker";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectTrigger,
  SelectValue
} from "@text-to-cad/ui/primitives/select";

export const FILE_SHEET_CONTROL_ROW_CLASSES = "space-y-1 px-2";
export const FILE_SHEET_ROW_STACK_CLASSES = "space-y-3";
export const FILE_SHEET_INLINE_CONTROL_ROW_CLASSES = "px-2";
// Section headers sit at the navbar's size (12px, normal weight) — a sheet's headings
// and the chrome above it read as the same level of structure. Row labels stay
// 11px muted, so a header separates from its rows by both size and colour.
export const FILE_SHEET_SECTION_TITLE_CLASSES = "text-xs text-sidebar-foreground";
export const FILE_SHEET_FIELD_LABEL_CLASSES = "block min-w-0 truncate text-tiny leading-4 text-muted-foreground";
export const FILE_SHEET_STATUS_TEXT_CLASSES = "px-2 text-tiny leading-4 text-muted-foreground";

// A trigger must clip and ellipsize its own value: the Radix trigger only sets
// whitespace-nowrap, so without this a long option pushes its chevron out
// through the border instead of truncating.
const FILE_SHEET_SELECT_TRIGGER_BASE_CLASSES = "!h-7 px-2 !text-tiny overflow-hidden [&_svg]:size-3.5 [&>span]:min-w-0 [&>span]:truncate";
export const FILE_SHEET_SELECT_TRIGGER_CLASSES = `${FILE_SHEET_SELECT_TRIGGER_BASE_CLASSES} w-full`;
// Inline triggers hug their value between two fixed bounds: never narrower than
// the standard control (the 80px value input / colour swatch) so a column of
// dropdowns, inputs and pickers shares one minimum size, and never wide enough
// to crowd the label. A percentage max-width cannot be used here — the wrapper
// is shrink-to-fit, so the percentage resolves against a width the trigger
// itself determines.
export const FILE_SHEET_INLINE_SELECT_TRIGGER_CLASSES = `${FILE_SHEET_SELECT_TRIGGER_BASE_CLASSES} w-fit min-w-20 max-w-44`;
export const FILE_SHEET_VALUE_BADGE_CLASSES = "shrink-0 rounded bg-muted px-1.5 py-0.5 font-mono text-micro leading-none tabular-nums text-muted-foreground";
export const FILE_SHEET_VALUE_BADGE_INPUT_CLASSES = [
  "h-7 w-20 shrink-0 rounded-md border border-input bg-transparent px-2 py-1 text-right text-tiny leading-none tabular-nums text-foreground shadow-xs outline-none",
  "m-0 box-border min-w-0 theme-none transition-[color,box-shadow,border-color] placeholder:text-muted-foreground",
  "focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50 disabled:opacity-50 dark:bg-input/30"
].join(" ");
export const FILE_SHEET_COMPACT_BUTTON_CLASSES = "h-7 px-2 text-tiny text-muted-foreground hover:text-foreground";
export const FILE_SHEET_COMPACT_INPUT_CLASSES = "!h-7 px-2 text-tiny !text-foreground";
export const FILE_SHEET_PRECISION_SLIDER_CLASSES = [
  "h-4",
  "[&_[data-slot=slider-track]]:h-px",
  "[&_[data-slot=slider-track]]:rounded-full",
  "[&_[data-slot=slider-track]]:bg-border",
  "[&_[data-slot=slider-range]]:bg-primary",
  "[&_[data-slot=slider-thumb]]:h-2.5",
  "[&_[data-slot=slider-thumb]]:w-1.5",
  "[&_[data-slot=slider-thumb]]:rounded-full",
  "[&_[data-slot=slider-thumb]]:border-primary",
  "[&_[data-slot=slider-thumb]]:bg-background",
  "[&_[data-slot=slider-thumb]]:shadow-none",
  "[&_[data-slot=slider-thumb]]:ring-0",
  "[&_[data-slot=slider-thumb]]:hover:border-primary/85",
  "[&_[data-slot=slider-thumb]]:hover:ring-1",
  "[&_[data-slot=slider-thumb]]:hover:ring-ring/25",
  "[&_[data-slot=slider-thumb]]:focus-visible:ring-2",
  "[&_[data-slot=slider-thumb]]:focus-visible:ring-ring/30"
].join(" ");

// A properties-panel section that is always visible: no disclosure affordance
// or hover treatment. Use for primary controls such as Mode and Projection.
/** A section heading: 28px, regular 12px, never a control (`docs/settings-ui.md`). */
export const FILE_SHEET_SECTION_HEADING_CLASSES = "flex min-h-7 items-center px-2 py-1 text-xs font-normal leading-4 text-foreground";

/**
 * One settings section: a heading and its rows, under a top border when another section
 * precedes it. `onOpenChange` makes the heading a disclosure: a Display feature gate
 * (`gated`: open IS enabled, and a shut gate mounts nothing) or a fold. `onReveal` is what a
 * press on an open section's title does (scroll the section into view).
 */
export function FileSheetSettingsSection({ title, children, open = true, onOpenChange,
  gated = false, onReveal, headingAction = null, sectionId }) {
  const titleId = useId();
  const contentId = useId();
  const collapsible = typeof onOpenChange === "function";
  return <section aria-labelledby={titleId} data-settings-section={sectionId} className="[&+section]:border-t border-border">
    <div data-settings-section-heading="" className="relative h-7 shrink-0">
      {collapsible ? <FileSheetToggleHeading title={title} open={open} onOpenChange={onOpenChange}
        headingId={titleId} contentId={contentId} onTitleClick={onReveal}
        verbs={gated ? ["Enable", "Disable"] : ["Expand", "Collapse"]} />
        : <h2>{onReveal ? <button id={titleId} type="button" onClick={onReveal}
          className={`${FILE_SHEET_SECTION_HEADING_CLASSES} w-full text-left`}>{title}</button>
          : <span id={titleId} className={FILE_SHEET_SECTION_HEADING_CLASSES}>{title}</span>}</h2>}
      {headingAction && <div className="absolute right-1 top-0 flex h-7 items-center gap-0.5">{headingAction}</div>}
    </div>
    <div id={contentId} hidden={!open} data-settings-section-body="" className="space-y-1 pb-2">{!gated || open ? children : null}</div>
  </section>;
}

// Expanded IS enabled. Only explicit activation changes settings: hover, focus,
// scrolling and another section moving under the pointer must never write state.
/**
 * The heading row of a section that opens and shuts: its title — shown muted, and a button
 * that opens it, while it is shut — and a trailing plus when shut and minus when open.
 * `verbs` name the two acts
 * for the button's label: `["Enable", "Disable"]` for a Display gate, `["Expand",
 * "Collapse"]` for a section a person folds away.
 */
function FileSheetToggleHeading({ title, open, onOpenChange, headingId, contentId, verbs, onTitleClick }) {
  const show = () => { onOpenChange(true); onTitleClick?.(); };
  const act = `${open ? verbs[1] : verbs[0]} ${title}`;
  return (
    <div className={cn("flex min-h-7 items-center", !open && "hover:bg-accent")}>
      <h2 className="min-w-0 flex-1">
        {open && onTitleClick ? <button id={headingId} type="button" aria-expanded={true} aria-controls={contentId}
          onClick={onTitleClick}
          className="flex min-h-7 w-full items-center px-2 py-1 text-left text-xs font-normal leading-4 text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring/45">{title}</button>
          : open ? <span id={headingId} className="flex min-h-7 items-center px-2 py-1 text-xs font-normal leading-4 text-foreground">{title}</span> : <button id={headingId} type="button" aria-expanded={false} aria-controls={contentId}
          onClick={show}
          className="flex min-h-7 w-full items-center px-2 py-1 text-left text-xs font-normal leading-4 text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring/45">
          {title}
        </button>}
      </h2>
      <Button type="button" variant="ghost" size="icon-xs" aria-label={act}
        aria-expanded={open} aria-controls={contentId}
        onClick={open ? () => onOpenChange(false) : show}
        className="mr-1 size-6 shrink-0 text-muted-foreground hover:text-foreground">
        {open ? <Minus className="size-3.5" strokeWidth={1.5} aria-hidden="true" /> : <Plus className="size-3.5" strokeWidth={1.5} aria-hidden="true" />}
      </Button>
    </div>
  );
}

export function FileSheetCheckboxRow({ label, checked, onCheckedChange, className }) {
  return (
    <label className={cn("flex min-h-6 cursor-pointer items-center gap-2 px-2 text-tiny text-muted-foreground", className)}>
      <input type="checkbox" checked={checked} onChange={event => onCheckedChange(event.target.checked)} className="size-3.5 shrink-0 accent-primary" />
      <span>{label}</span>
    </label>
  );
}

// Figma-like property: the icon/unit carries the visible meaning; its accessible
// name and shared hover hint keep the exact setting discoverable.
export function FileSheetNumberProperty({ label, Icon, value, onValueCommit }) {
  return (
    <TooltipHint content={label}><div  className="flex h-7 min-w-0 items-center gap-1 rounded-md border border-input bg-muted/30 px-2 focus-within:ring-1 focus-within:ring-ring">
      {Icon ? <Icon className="size-3.5 shrink-0 text-muted-foreground" aria-hidden="true" /> : null}
      <FileSheetValueInput ariaLabel={`${label} value`} value={value} onValueCommit={onValueCommit}
        className="h-6 min-w-0 flex-1 rounded-none border-0 bg-transparent p-0 text-left shadow-none focus-visible:ring-0 dark:bg-transparent" />
    </div></TooltipHint>
  );
}

export function FileSheetColorProperty({ label, value, onChange, opacity, onOpacityChange, className }) {
  const withOpacity = typeof onOpacityChange === "function";
  return (
    <div className={cn("min-w-0 px-2", className)}>
      <TooltipHint content={label}><div className="flex h-7 min-w-0 items-center overflow-hidden rounded-md border border-input bg-muted/30">
        <FileSheetColorPicker value={value} onChange={onChange} opacity={opacity} onOpacityChange={onOpacityChange}
          showOpacity={withOpacity} aria-label={label}
          className="min-w-0 flex-1 rounded-none border-0 bg-transparent shadow-none dark:bg-transparent" />

      </div></TooltipHint>
    </div>
  );
}

export function FileSheetSubsection({ title, children, contentClassName }) {
  // A gated section collapses to its heading alone. The heading's bottom gap
  // exists to separate it from the first row, so with no rows it must go —
  // otherwise a collapsed section carries 16px above its heading and 24px
  // below, which is where the padding visibly stopped being even.
  const hasRows = Children.toArray(children).length > 0;
  return (
    // The rule belongs to the top of a section, so a section owns the gap below
    // its own last row (pb-4) and the rule owns the gap down to the heading
    // (mb-4). Both are 16px, which is what makes the space above a heading and
    // below a section's last row read as equal. Inside, rows sit 12px apart and
    // the heading takes 12px to clear them.
    <div className="pb-4 first:pt-2 first:[&_.cad-sheet-subsection-separator]:hidden">
      <div className="cad-sheet-subsection-separator mx-2 mb-4 h-px bg-border/60" />
      {/* Titleless subsections are a rule plus rows: for a couple of settings
          that belong to the sheet as a whole rather than to any named group, and
          would otherwise need a heading invented for them. */}
      {title ? (
        <div
          className={cn(
            "flex min-h-5 min-w-0 items-center justify-between gap-2 px-2",
            hasRows && "pb-3"
          )}
        >
          <span className={cn("min-w-0 truncate leading-4", FILE_SHEET_SECTION_TITLE_CLASSES)}>{title}</span>
        </div>
      ) : null}
      {hasRows ? <div className={cn(FILE_SHEET_ROW_STACK_CLASSES, contentClassName)}>{children}</div> : null}
    </div>
  );
}

export function FileSheetControlRow({ label, value, trailing, children, className }) {
  // A row whose control lives in the trailing slot (a color picker, a value
  // readout) has no block content. Rendering the content div anyway left an
  // empty box carrying the stack's 4px top margin, so those rows stood 4px
  // taller than every switch row beside them.
  const hasContent = Children.toArray(children).length > 0;
  return (
    <div className={cn(FILE_SHEET_CONTROL_ROW_CLASSES, className)}>
      {label != null || value != null || trailing != null ? (
        <div
          className={cn(
            "flex items-center justify-between gap-2",
            hasContent ? "min-h-4" : "min-h-7"
          )}
        >
          {label != null ? (
            <span className={FILE_SHEET_FIELD_LABEL_CLASSES}>{label}</span>
          ) : <span />}
          {trailing != null ? trailing : value != null ? (
            <span className={FILE_SHEET_VALUE_BADGE_CLASSES}>{value}</span>
          ) : null}
        </div>
      ) : null}
      {hasContent ? (
        <div className="min-w-0">{children}</div>
      ) : null}
    </div>
  );
}

export function parseFileSheetNumberInput(value, {
  fallback = 0,
  min = -Infinity,
  max = Infinity,
  integer = false
} = {}) {
  const text = String(value ?? "").trim();
  const match = text.match(/[+-]?(?:\d+\.?\d*|\.\d+)(?:e[+-]?\d+)?/i);
  const fallbackValue = Number.isFinite(Number(fallback)) ? Number(fallback) : 0;
  const numericValue = match ? Number(match[0]) : NaN;
  const lowerBound = Number.isFinite(Number(min)) ? Number(min) : -Infinity;
  const upperBound = Number.isFinite(Number(max)) ? Number(max) : Infinity;
  const resolvedValue = Number.isFinite(numericValue) ? numericValue : fallbackValue;
  const clampedValue = Math.min(Math.max(resolvedValue, lowerBound), Math.max(lowerBound, upperBound));
  return integer ? Math.round(clampedValue) : clampedValue;
}

export function FileSheetValueInput({
  value,
  onValueCommit,
  disabled = false,
  ariaLabel,
  inputMode = "decimal",
  className
}) {
  const inputRef = useRef(null);
  const displayValue = String(value ?? "");
  const [draftValue, setDraftValue] = useState(displayValue);
  const [editing, setEditing] = useState(false);
  const skipCommitRef = useRef(false);
  const selectOnEditRef = useRef(false);
  const visibleValue = editing ? draftValue : displayValue;

  useEffect(() => {
    if (!editing) {
      setDraftValue(displayValue);
    }
  }, [displayValue, editing]);

  useEffect(() => {
    if (!editing || !selectOnEditRef.current) {
      return;
    }
    selectOnEditRef.current = false;
    inputRef.current?.select?.();
  }, [editing, visibleValue]);

  const pendingSelectFrameRef = useRef(0);
  const selectInputValue = (input) => {
    input?.select?.();
    if (typeof window !== "undefined") {
      // The deferred re-select exists for the format swap on focus ("2.0 mm" -> "2"). It
      // must die the moment the user types: firing after the first keystroke re-selects the
      // typed digit, and the second keystroke then overwrites the first.
      window.cancelAnimationFrame?.(pendingSelectFrameRef.current);
      pendingSelectFrameRef.current = window.requestAnimationFrame?.(() => {
        if (selectOnEditRef.current === false) {
          return;
        }
        input?.select?.();
      }) || 0;
    }
  };

  return (
    <input
      ref={inputRef}
      type="text"
      inputMode={inputMode}
      value={visibleValue}
      disabled={disabled}
      onChange={(event) => {
        // Typing cancels every pending select — the selection belongs to focus, never to a
        // frame that lands mid-word.
        selectOnEditRef.current = false;
        if (typeof window !== "undefined") {
          window.cancelAnimationFrame?.(pendingSelectFrameRef.current);
        }
        setDraftValue(event.target.value);
      }}
      onFocus={(event) => {
        selectOnEditRef.current = true;
        setEditing(true);
        selectInputValue(event.currentTarget);
      }}
      onClick={(event) => {
        selectOnEditRef.current = true;
        setEditing(true);
        selectInputValue(event.currentTarget);
      }}
      onMouseUp={(event) => {
        event.preventDefault();
      }}
      onBlur={() => {
        setEditing(false);
        if (skipCommitRef.current) {
          skipCommitRef.current = false;
          return;
        }
        onValueCommit?.(draftValue);
      }}
      onKeyDown={(event) => {
        if (event.key === "Enter") {
          // Enter commits HERE rather than delegating to the blur. `blur()` only fires an
          // event when the input is the active element, so an Enter that arrives when it is
          // not — a re-render that replaced the node, a host that moved focus — used to leave
          // the edit sitting in the draft, looking typed but applying to nothing, until some
          // later focus change flushed it into whatever the person had moved on to.
          const input = event.currentTarget;
          event.preventDefault();
          setEditing(false);
          onValueCommit?.(draftValue);
          // The blur this asks for must not commit the same edit a second time — the same
          // handshake Escape uses. If no blur runs, the guard is disarmed again, or it would
          // swallow the NEXT commit instead of this one.
          skipCommitRef.current = true;
          input.blur();
          if (typeof document !== "undefined" && document.activeElement === input) {
            skipCommitRef.current = false;
          }
        }
        if (event.key === "Escape") {
          event.preventDefault();
          skipCommitRef.current = true;
          setDraftValue(displayValue);
          event.currentTarget.blur();
        }
      }}
      className={cn(
        FILE_SHEET_VALUE_BADGE_INPUT_CLASSES,
        className
      )}
      style={{ borderColor: editing ? "var(--ring)" : undefined }}
      aria-label={ariaLabel}
    />
  );
}

// The value box's width: as narrow as a joint's figure allows — an angle ("-102°", "0.00°") fits
// five characters, a length with its unit ("0.00 mm") seven — so a unit is never cut off.
const valueInputWidth = value => {
  const length = String(value ?? "").length;
  return length <= 5 ? "w-[calc(5ch+0.75rem)]" : length <= 7 ? "w-[calc(7ch+0.75rem)]" : "w-[calc(9ch+0.75rem)]";
};

/**
 * A slider row (a joint of Position), compact: its label tight above its slider in the flexible
 * left column, and a small committed value input (24px tall, as wide as its figure and unit need,
 * its figures tabular) in the right column (`docs/settings-ui.md`).
 */
export function FileSheetSliderField({ label, value, onValueCommit, valueInputProps, labelTitle, children }) {
  return <FileSheetControlRow>
    <div className="grid min-h-7 min-w-0 grid-cols-[minmax(0,1fr)_auto] items-center gap-1.5" data-position-control="">
      <div className="min-w-0">
        {label != null ? <TooltipHint content={labelTitle || label} overflowOnly><span className={cn(FILE_SHEET_FIELD_LABEL_CLASSES, "leading-3")}>{label}</span></TooltipHint> : null}
        {/* Tight under its label: the slider's own box is taller than its track, so it is pulled up
            until its thumb's top meets the label's foot. */}
        <div className="-mt-0.5 min-w-0">{children}</div>
      </div>
      {onValueCommit ? <FileSheetValueInput value={value} onValueCommit={onValueCommit} {...valueInputProps}
        className={cn("h-6 px-1.5", valueInputWidth(value), valueInputProps?.className)} /> : null}
    </div>
  </FileSheetControlRow>;
}

export function FileSheetInlineControlRow({ label, children, className }) {
  return (
    <div className={cn(FILE_SHEET_INLINE_CONTROL_ROW_CLASSES, className)}>
      <div className="flex min-h-7 max-w-full items-center justify-between gap-2">
        <span className={FILE_SHEET_FIELD_LABEL_CLASSES}>{label}</span>
        <span className="shrink-0">{children}</span>
      </div>
    </div>
  );
}

// Loading / empty / info line, or an error with tone="error". The one style
// for every in-sheet message.
export function FileSheetStatusText({ children, tone = "muted", className }) {
  return (
    <p
      className={cn(
        FILE_SHEET_STATUS_TEXT_CLASSES,
        tone === "error" && "whitespace-pre-line text-destructive",
        className
      )}
    >
      {children}
    </p>
  );
}

// Read-only fact in a field grid: same silhouette as an input, muted fill so it
// reads as data, not an editable control.
export function FileSheetValueField({ label, value }) {
  const displayValue = String(value ?? "");
  return (
    <div className="block min-w-0">
      <span className={FILE_SHEET_FIELD_LABEL_CLASSES}>{label}</span>
      <TooltipHint content={displayValue} overflowOnly><div
        className="mt-1 min-h-7 truncate rounded-md border border-border/70 bg-muted/25 px-2 py-1 text-tiny leading-4 text-foreground">
        {displayValue}
      </div></TooltipHint>
    </div>
  );
}

export function FileSheetFieldGrid({ columns = 2, children, className }) {
  return (
    <div
      className={cn("grid gap-1 px-2", className)}
      style={{ gridTemplateColumns: typeof columns === "number" ? `repeat(${columns}, minmax(0, 1fr))` : columns }}
    >
      {children}
    </div>
  );
}

// Sibling actions as equal-width columns; a single child renders full width.
export function FileSheetButtonRow({ children }) {
  const columnCount = Math.max(1, Children.count(children));
  return (
    <div
      className="grid gap-1.5 px-2"
      style={{ gridTemplateColumns: `repeat(${columnCount}, minmax(0, 1fr))` }}
    >
      {children}
    </div>
  );
}

// The standard select: an inline row, trigger on the control axis; `hideLabel` is the
// trigger alone, full width, its label its accessible name.
// Pass triggerContent to replace the plain SelectValue (e.g. a swatch + label).
export function FileSheetSelectRow({
  label,
  value,
  onValueChange,
  options,
  ariaLabel,
  placeholder,
  triggerContent,
  hideLabel = false,
  triggerClassName,
  className
}) {
  const selectedIcon = options.find(option => option.value === value)?.icon;
  const select = (
    <Select value={value} onValueChange={onValueChange}>
      <TooltipHint content={hideLabel ? ariaLabel || label : undefined}><SelectTrigger
        size="sm"
        className={cn(hideLabel ? FILE_SHEET_SELECT_TRIGGER_CLASSES : FILE_SHEET_INLINE_SELECT_TRIGGER_CLASSES, triggerClassName)}

        aria-label={ariaLabel || (typeof label === "string" ? label : undefined)}
      >
        {triggerContent ?? (selectedIcon ? <span className="flex min-w-0 items-center gap-1">{selectedIcon}<SelectValue placeholder={placeholder} /></span> : <SelectValue placeholder={placeholder} />)}
      </SelectTrigger></TooltipHint>
      <SelectContent>
        {(() => {
          // Options may carry a `group`: grouped ones render under SelectGroup headings in
          // first-appearance order, ungrouped ones (e.g. a leading "None") stay at the top.
          const renderItem = (option) => (
            <TooltipHint key={option.value} content={option.title}><SelectItem

              value={option.value}
              disabled={option.disabled}

              icon={option.icon}
            >
              {option.label}
            </SelectItem></TooltipHint>
          );
          const ungrouped = options.filter((option) => !option.group);
          const groupNames = [...new Set(options.map((option) => option.group).filter(Boolean))];
          if (!groupNames.length) {
            return options.map(renderItem);
          }
          return (
            <>
              {ungrouped.map(renderItem)}
              {groupNames.map((groupName) => (
                <SelectGroup key={groupName}>
                  <SelectLabel className="text-micro uppercase tracking-wide text-muted-foreground">
                    {groupName}
                  </SelectLabel>
                  {options.filter((option) => option.group === groupName).map(renderItem)}
                </SelectGroup>
              ))}
            </>
          );
        })()}
      </SelectContent>
    </Select>
  );
  if (hideLabel) return <div className={cn("min-w-0 px-2", className)}>{select}</div>;
  return (
    <FileSheetInlineControlRow label={label} className={className}>
      {select}
    </FileSheetInlineControlRow>
  );
}

// Compact color picker trigger for inline rows and parameter rows.
export function FileSheetColorPicker({
  value,
  onChange,
  className,
  swatchClassName,
  ...props
}) {
  return (
    <ColorPicker
      value={value}
      onChange={onChange}
      className={cn(
        FILE_SHEET_COMPACT_INPUT_CLASSES,
        "w-fit justify-start gap-1.5 px-1.5",
        className
      )}
      swatchClassName={cn("size-3.5", swatchClassName)}
      popoverAlign="end"
      {...props}
    />
  );
}
