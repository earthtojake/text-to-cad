import { TooltipHint } from "@hardcore/ui/primitives/tooltip";
import { Children, createContext, useContext, useEffect, useId, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Minus, Plus } from "lucide-react";
import { cn } from "@hardcore/ui/utils";
import { Button } from "@hardcore/ui/primitives/button";
import { ColorPicker } from "@hardcore/ui/primitives/color-picker";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectTrigger,
  SelectValue
} from "@hardcore/ui/primitives/select";

const FILE_SHEET_CONTROL_TEXT_CLASSES = [
  "[&_[data-slot=input]]:!text-tiny",
  "[&_[data-slot=select-trigger]]:!text-tiny",
  "[&_[data-slot=color-picker-trigger]]:!text-tiny"
].join(" ");

export const FILE_SHEET_CONTROL_ROW_CLASSES = "space-y-1 px-2";
export const FILE_SHEET_ROW_STACK_CLASSES = "space-y-3";
export const FILE_SHEET_SLIDER_FIELD_CLASSES = "space-y-1 px-2";
export const FILE_SHEET_INLINE_CONTROL_ROW_CLASSES = "px-2";
// Section headers sit at the navbar's size (12px, normal weight) — a sheet's headings
// and the chrome above it read as the same level of structure. Row labels stay
// 11px muted, so a header separates from its rows by both size and colour.
export const FILE_SHEET_SECTION_TITLE_CLASSES = "text-xs text-sidebar-foreground";
export const FILE_SHEET_FIELD_LABEL_CLASSES = "block min-w-0 truncate text-tiny leading-4 text-muted-foreground";
export const FILE_SHEET_STATUS_TEXT_CLASSES = "px-2 text-tiny leading-4 text-muted-foreground";
/** Host-owned panel content slot. Without a slot, render a plain fallback aside. */
export const HostPanelSlotContext = createContext(null);

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

/** One section primitive for Display, file panels and standalone settings. */
export function FileSheetSettingsSection({ title, children, open = true, onOpenChange,
  gated = false, disabled = false, onReveal, headingAction = null, hideHeading = false, sectionId, index = 0, count = 1, sticky = false }) {
  const titleId = useId();
  const contentId = useId();
  const collapsible = typeof onOpenChange === "function";
  // Contents keeps sticky headings in the panel's shared scroll flow.
  return <section aria-labelledby={titleId} data-file-panel-section={sectionId}
    className={sticky ? "contents" : "[&+section]:border-t border-border"}>
    <div hidden={hideHeading} data-mobile-panel-top-row={index === 0 ? "" : undefined} data-file-panel-heading="" className={cn("relative h-7 shrink-0 bg-background",
      sticky && "sticky z-10", sticky && index > 0 && "border-t border-border")}
      style={sticky ? { top: `${index * 1.75}rem`, bottom: `${(count - index - 1) * 1.75}rem` } : undefined}>
      {collapsible ? <FileSheetToggleHeading as="h2" title={title} open={open} onOpenChange={onOpenChange}
        headingId={titleId} contentId={contentId} disabled={disabled} onTitleClick={onReveal}
        verbs={gated ? ["Enable", "Disable"] : ["Expand", "Collapse"]} />
        : <h2>{onReveal ? <button id={titleId} type="button" onClick={onReveal}
          className={`${FILE_SHEET_SECTION_HEADING_CLASSES} w-full text-left`}>{title}</button>
          : <span id={titleId} className={FILE_SHEET_SECTION_HEADING_CLASSES}>{title}</span>}</h2>}
      {headingAction && <div className="absolute right-1 top-0 flex h-7 items-center">{headingAction}</div>}
    </div>
    <div id={contentId} hidden={!open} data-file-panel-body="" className={cn("space-y-1 pb-2",
      !hideHeading && "[&>div>[data-slot=tree-filter]]:h-8 [&>div>[data-slot=tree-filter]]:pb-1")}>{!gated || open ? children : null}</div>
  </section>;
}

export function FileSheetStaticSection({ title, children }) {
  return <FileSheetSettingsSection title={title}>{children}</FileSheetSettingsSection>;
}

// Expanded IS enabled. Only explicit activation changes settings: hover, focus,
// scrolling and another section moving under the pointer must never write state.
/**
 * The heading row of a section that opens and shuts: its title — shown muted, and a button
 * that opens it, while it is shut — and a trailing plus when shut and minus when open.
 * `verbs` name the two acts
 * for the button's label: `["Enable", "Disable"]` for a Display gate, `["Expand",
 * "Collapse"]` for a file panel's section a person folds away.
 */
export function FileSheetToggleHeading({ title, open, onOpenChange, headingId, contentId, verbs, disabled = false, onTitleClick, as: Heading = "h3" }) {
  const show = () => { if (!disabled) { onOpenChange(true); onTitleClick?.(); } };
  const act = `${open ? verbs[1] : verbs[0]} ${title}`;
  return (
    <div className={cn("flex min-h-7 items-center", !open && !disabled && "hover:bg-accent", disabled && "opacity-40")}>
      <Heading className="min-w-0 flex-1">
        {open && onTitleClick ? <button id={headingId} type="button" disabled={disabled} aria-expanded={true} aria-controls={contentId}
          onClick={onTitleClick}
          className="flex min-h-7 w-full items-center px-2 py-1 text-left text-xs font-normal leading-4 text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring/45">{title}</button>
          : open ? <span id={headingId} className="flex min-h-7 items-center px-2 py-1 text-xs font-normal leading-4 text-foreground">{title}</span> : <button id={headingId} type="button" disabled={disabled} aria-expanded={false} aria-controls={contentId}
          onClick={show}
          className="flex min-h-7 w-full items-center px-2 py-1 text-left text-xs font-normal leading-4 text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring/45">
          {title}
        </button>}
      </Heading>
      <Button type="button" variant="ghost" size="icon-xs" aria-label={act}
        disabled={disabled} aria-expanded={open} aria-controls={contentId}
        onClick={open ? () => onOpenChange(false) : show}
        className="mr-1 size-6 shrink-0 text-muted-foreground hover:text-foreground">
        {open ? <Minus className="size-3.5" strokeWidth={1.5} aria-hidden="true" /> : <Plus className="size-3.5" strokeWidth={1.5} aria-hidden="true" />}
      </Button>
    </div>
  );
}

export function FileSheetGatedSection({ title, enabled, onEnabledChange, children }) {
  return <FileSheetSettingsSection title={title} open={enabled} onOpenChange={onEnabledChange} gated>{children}</FileSheetSettingsSection>;
}

export function FileSheetCheckboxRow({ label, checked, onCheckedChange, disabled = false, title, className }) {
  return (
    <TooltipHint content={title}><label  className={cn("flex min-h-6 cursor-pointer items-center gap-2 px-2 text-tiny text-muted-foreground has-disabled:cursor-default has-disabled:opacity-40", className)}>
      <input type="checkbox" checked={checked} disabled={disabled} onChange={event => onCheckedChange(event.target.checked)} className="size-3.5 shrink-0 accent-primary" />
      <span>{label}</span>
    </label></TooltipHint>
  );
}

// Figma-like property: the icon/unit carries the visible meaning; its accessible
// name and shared hover hint keep the exact setting discoverable.
export function FileSheetNumberProperty({ label, Icon, value, onValueCommit, disabled = false }) {
  return (
    <TooltipHint content={label}><div  className="flex h-7 min-w-0 items-center gap-1 rounded-md border border-input bg-muted/30 px-2 focus-within:ring-1 focus-within:ring-ring">
      {Icon ? <Icon className="size-3.5 shrink-0 text-muted-foreground" aria-hidden="true" /> : null}
      <FileSheetValueInput ariaLabel={`${label} value`} value={value} onValueCommit={onValueCommit} disabled={disabled}
        className="h-6 min-w-0 flex-1 rounded-none border-0 bg-transparent p-0 text-left shadow-none focus-visible:ring-0 dark:bg-transparent" />
    </div></TooltipHint>
  );
}

export function FileSheetColorProperty({ label, value, onChange, opacity, onOpacityChange, disabled = false, className }) {
  const withOpacity = typeof onOpacityChange === "function";
  return (
    <div className={cn("min-w-0 px-2", className)}>
      <TooltipHint content={label} disabled={disabled}><div className="flex h-7 min-w-0 items-center overflow-hidden rounded-md border border-input bg-muted/30">
        <FileSheetColorPicker value={value} onChange={onChange} opacity={opacity} onOpacityChange={onOpacityChange}
          showOpacity={withOpacity} disabled={disabled} aria-label={label}
          className="min-w-0 flex-1 rounded-none border-0 bg-transparent shadow-none dark:bg-transparent" />

      </div></TooltipHint>
    </div>
  );
}

export function FileSheetSubsection({
  title,
  trailing = null,
  children,
  className,
  contentClassName,
  hideFirstSeparator = true
}) {
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
    <div
      className={cn(
        "pb-4",
        hideFirstSeparator && "first:pt-2 first:[&_.cad-sheet-subsection-separator]:hidden",
        className
      )}
    >
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
          {/* Trailing holds the section's control — most often its gate switch,
              kept on the shared right-edge control axis like every other row. */}
          {trailing ? <span className="flex shrink-0 items-center">{trailing}</span> : null}
        </div>
      ) : null}
      {hasRows ? (
        <div
          className={cn(FILE_SHEET_ROW_STACK_CLASSES, contentClassName)}
          data-file-sheet-row-stack=""
        >
          {children}
        </div>
      ) : null}
    </div>
  );
}

export function FileSheetControlRow({
  label,
  value,
  trailing,
  children,
  className,
  contentClassName,
  labelClassName,
  rowKind = "control"
}) {
  // A row whose control lives in the trailing slot (a color picker, a value
  // readout) has no block content. Rendering the content div anyway left an
  // empty box carrying the stack's 4px top margin, so those rows stood 4px
  // taller than every switch row beside them.
  const hasContent = Children.toArray(children).length > 0;
  return (
    <div
      className={cn(FILE_SHEET_CONTROL_ROW_CLASSES, className)}
      data-file-sheet-control-row=""
      data-file-sheet-row-kind={rowKind}
    >
      {label != null || value != null || trailing != null ? (
        <div
          className={cn(
            "flex items-center justify-between gap-2",
            hasContent ? "min-h-4" : "min-h-7"
          )}
        >
          {label != null ? (
            <span className={cn(FILE_SHEET_FIELD_LABEL_CLASSES, labelClassName)}>{label}</span>
          ) : <span />}
          {trailing != null ? trailing : value != null ? (
            <span className={FILE_SHEET_VALUE_BADGE_CLASSES}>{value}</span>
          ) : null}
        </div>
      ) : null}
      {hasContent ? (
        <div className={cn("min-w-0", contentClassName)}>{children}</div>
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
  title,
  className,
  style
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
    <TooltipHint content={title}><input
      ref={inputRef}
      type="text"
      inputMode={inputMode}

      value={visibleValue}
      disabled={disabled}
      data-editing={editing ? "true" : "false"}
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
      style={{
        borderColor: editing ? "var(--ring)" : undefined,
        ...style
      }}
      aria-label={ariaLabel}
    /></TooltipHint>
  );
}

export function FileSheetSliderField({
  label,
  value,
  trailing,
  onValueCommit,
  valueInputProps,
  children,
  className,
  contentClassName,
  labelClassName,
  labelTitle,
  compact = false,
  stacked = false,
  hideLabel = false
}) {
  const valueTrailing = trailing ?? (onValueCommit ? (
    <FileSheetValueInput
      value={value}
      onValueCommit={onValueCommit}
      {...valueInputProps}
    />
  ) : null);

  if (stacked) {
    return <FileSheetControlRow className={className} rowKind="slider">
      <div className="grid min-h-8 min-w-0 grid-cols-[minmax(0,1fr)_auto] items-center gap-2" data-position-control=""
        >
        <div className="min-w-0">
          {!hideLabel && label != null ? <TooltipHint content={labelTitle || label} overflowOnly><span className={cn(FILE_SHEET_FIELD_LABEL_CLASSES, "leading-3")}>{label}</span></TooltipHint> : null}
          <div className="min-w-0">{children}</div>
        </div>
        {valueTrailing}
      </div>
    </FileSheetControlRow>;
  }
  if (compact) {
    return (
      <div className={cn("px-2", className)} >
        <div className={cn("flex min-h-7 items-center gap-2", contentClassName)}>
          {!hideLabel && label != null ? <TooltipHint content={labelTitle || label} overflowOnly><span className={cn("min-w-0 max-w-[40%] truncate text-tiny text-muted-foreground", labelClassName)}>{label}</span></TooltipHint> : null}
          <div className="min-w-12 flex-1">{children}</div>
          {valueTrailing}
        </div>
      </div>
    );
  }
  return (
    <FileSheetControlRow
      label={valueTrailing ? null : label}
      value={null}
      className={cn(FILE_SHEET_SLIDER_FIELD_CLASSES, className)}
      contentClassName={cn(valueTrailing ? "space-y-0" : "space-y-1", contentClassName)}
      labelClassName={labelClassName}
      rowKind="slider"
    >
      {valueTrailing ? (
        <div
          className="grid min-w-0 grid-cols-[minmax(0,1fr)_auto] items-center gap-x-2"
          data-file-sheet-slider-input-row=""
        >
          <div className="min-w-0 pr-3">
            {label != null ? (
              <span
                className={cn(
                  FILE_SHEET_FIELD_LABEL_CLASSES,
                  "block h-3 leading-3",
                  labelClassName
                )}
              >
                {label}
              </span>
            ) : null}
            <div className={cn("min-w-0", label != null && "-mt-0.5")}>
              {children}
            </div>
          </div>
          {valueTrailing}
        </div>
      ) : children}
    </FileSheetControlRow>
  );
}

export function FileSheetInlineControlRow({
  label,
  description,
  children,
  className,
  labelClassName
}) {
  return (
    <div
      className={cn(FILE_SHEET_INLINE_CONTROL_ROW_CLASSES, className)}
      data-file-sheet-control-row=""
      data-file-sheet-row-kind="inline"
    >
      <div className="flex min-h-7 max-w-full items-center justify-between gap-2">
        <span className={cn(FILE_SHEET_FIELD_LABEL_CLASSES, labelClassName)}>{label}</span>
        <span className="shrink-0">{children}</span>
      </div>
      {description ? (
        <p className="mt-0.5 max-w-[28rem] text-tiny leading-4 text-muted-foreground">{description}</p>
      ) : null}
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
export function FileSheetValueField({ label, value, mono = false }) {
  const displayValue = String(value ?? "");
  return (
    <div className="block min-w-0">
      <span className={FILE_SHEET_FIELD_LABEL_CLASSES}>{label}</span>
      <TooltipHint content={displayValue} overflowOnly><div
        className={cn(
          "mt-1 min-h-7 truncate rounded-md border border-border/70 bg-muted/25 px-2 py-1 text-tiny leading-4 text-foreground",
          mono && "font-mono tabular-nums"
        )}

      >
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
      data-file-sheet-field-grid=""
    >
      {children}
    </div>
  );
}

// Sibling actions as equal-width columns; a single child renders full width.
export function FileSheetButtonRow({ children, columns, className }) {
  const columnCount = Math.max(1, columns || Children.count(children));
  return (
    <div
      className={cn("grid gap-1.5 px-2", className)}
      style={{ gridTemplateColumns: `repeat(${columnCount}, minmax(0, 1fr))` }}
      data-file-sheet-button-row=""
    >
      {children}
    </div>
  );
}

// The standard select: an inline row, trigger on the control axis. `stacked`
// gives the block-row treatment — label above, full width — and is reserved for
// a surface's primary control, the first row that reframes everything under it.
// Nothing else.
// Pass triggerContent to replace the plain SelectValue (e.g. a swatch + label).
export function FileSheetSelectRow({
  label,
  value,
  onValueChange,
  options,
  ariaLabel,
  disabled = false,
  placeholder,
  triggerContent,
  stacked = false,
  hideLabel = false,
  triggerClassName,
  className
}) {
  const selectedIcon = options.find(option => option.value === value)?.icon;
  const select = (
    <Select value={value} onValueChange={onValueChange} disabled={disabled}>
      <TooltipHint content={hideLabel ? ariaLabel || label : undefined}><SelectTrigger
        size="sm"
        className={cn(stacked || hideLabel ? FILE_SHEET_SELECT_TRIGGER_CLASSES : FILE_SHEET_INLINE_SELECT_TRIGGER_CLASSES, triggerClassName)}

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
  if (stacked) {
    return (
      <FileSheetControlRow label={label} className={className}>
        {select}
      </FileSheetControlRow>
    );
  }
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

/** A file's own panel, portaled into the host's panel column; its sections own their scrolling. */
export default function FileSheet({ open, title, children }) {
  const hostPanelSlot = useContext(HostPanelSlotContext);
  // FileViewer owns the single column and its dimensions. Wait for its slot.
  return open && hostPanelSlot
    ? createPortal(<div className="flex h-full min-h-0 flex-col" data-file-sheet={title || ""}>
      <div className={cn("flex min-h-0 flex-1 flex-col", FILE_SHEET_CONTROL_TEXT_CLASSES)}>{children}</div>
    </div>, hostPanelSlot)
    : null;
}
