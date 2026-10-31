import { TooltipHint } from "@text-to-cad/ui/primitives/tooltip";
import { Children, useEffect, useId, useRef, useState } from "react";
import { cn } from "@text-to-cad/ui/utils";
import { Checkbox } from "@text-to-cad/ui/primitives/checkbox";
import { ColorPicker } from "@text-to-cad/ui/primitives/color-picker";
import { useI18n } from "@text-to-cad/ui/i18n";

export const FILE_SHEET_CONTROL_ROW_CLASSES = "space-y-1 px-2";
export const FILE_SHEET_ROW_STACK_CLASSES = "space-y-3";
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
export const FILE_SHEET_VALUE_BADGE_CLASSES = "shrink-0 rounded bg-muted px-1.5 py-0.5 font-mono text-micro leading-none tabular-nums text-muted-foreground";
export const FILE_SHEET_VALUE_BADGE_INPUT_CLASSES = [
  "h-7 w-20 shrink-0 rounded-md border border-input bg-transparent px-2 py-1 text-right text-tiny leading-none tabular-nums text-foreground shadow-xs outline-none",
  "m-0 box-border min-w-0 theme-none transition-[color,box-shadow,border-color] placeholder:text-muted-foreground",
  "focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50 disabled:opacity-50 dark:bg-input/30"
].join(" ");
export const FILE_SHEET_COMPACT_INPUT_CLASSES = "!h-7 px-2 text-tiny !text-foreground";
// A joint's slider: in its row's 16px band, with no fill — a joint's zero is mostly mid-range, so a
// bar from the left end up to the thumb would mean nothing.
export const FILE_SHEET_PRECISION_SLIDER_CLASSES = "h-4 [&_[data-slot=slider-range]]:hidden";

/** A section heading: 24px, regular 11px, never a disclosure (`docs/settings-ui.md`). */
export const FILE_SHEET_SECTION_HEADING_CLASSES = "flex h-6 min-w-0 items-center gap-2 px-2 text-tiny font-normal leading-4 text-foreground";

/**
 * One settings section: a heading and its rows, a rule above it when another section precedes
 * it. A section a feature switches on and off (`enabled`, `onEnabledChange`) ends its heading in
 * that feature's checkbox, at the right, the title naming it; while it is off the section is its
 * heading alone.
 */
export function FileSheetSettingsSection({ title, children, enabled, onEnabledChange, sectionId }) {
  const titleId = useId();
  const switchable = typeof onEnabledChange === "function";
  const open = !switchable || enabled === true;
  return <section aria-labelledby={titleId} data-settings-section={sectionId}
    className="[&+section]:mt-1 [&+section]:border-t [&+section]:pt-1 border-border">
    <h2 className="m-0">
      {switchable ? <label className={cn(FILE_SHEET_SECTION_HEADING_CLASSES, "cursor-pointer justify-between")}>
        <span id={titleId} className="truncate">{title}</span>
        <Checkbox aria-labelledby={titleId} checked={open} onCheckedChange={checked => onEnabledChange(checked === true)} />
      </label> : <span id={titleId} className={FILE_SHEET_SECTION_HEADING_CLASSES}>{title}</span>}
    </h2>
    {children == null || !open ? null : <div data-settings-section-body="" className="space-y-1 pb-1">{children}</div>}
  </section>;
}

/**
 * A setting's row: its label in a fixed column and its control filling the rest, 24px, so the
 * controls of a form start on one line. The label may be the section-local short name ("Opacity"
 * under Grid); the control keeps the full accessible name.
 */
export function FileSheetSettingRow({ label, children, disabled = false, className }) {
  return <div className={cn("grid h-6 min-w-0 grid-cols-[4rem_minmax(0,1fr)] items-center gap-2 px-2", className)}>
    <TooltipHint content={label} overflowOnly><span className={cn(FILE_SHEET_FIELD_LABEL_CLASSES, disabled && "opacity-50")}>{label}</span></TooltipHint>
    <div className="flex min-w-0 items-center gap-1">{children}</div>
  </div>;
}

// Figma-like property: the icon/unit carries the visible meaning; its accessible
// name and shared hover hint keep the exact setting discoverable.
export function FileSheetNumberProperty({ label, Icon, value, onValueCommit }) {
  const { t } = useI18n();
  return (
    <TooltipHint content={label}><div  className="flex h-7 min-w-0 items-center gap-1 rounded-md border border-input bg-muted/30 px-2 focus-within:ring-1 focus-within:ring-ring">
      {Icon ? <Icon className="size-3.5 shrink-0 text-muted-foreground" aria-hidden="true" /> : null}
      <FileSheetValueInput ariaLabel={t("field.value", { name: label })} value={value} onValueCommit={onValueCommit}
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
        {label != null ? <TooltipHint content={labelTitle || label} overflowOnly><span data-file-sheet-field-label="" className={cn(FILE_SHEET_FIELD_LABEL_CLASSES, "leading-3")}>{label}</span></TooltipHint> : null}
        {/* Under its label, its thumb clear of the label's foot. */}
        <div className="mt-1 min-w-0">{children}</div>
      </div>
      {onValueCommit ? <FileSheetValueInput value={value} onValueCommit={onValueCommit} {...valueInputProps}
        className={cn("h-6 px-1.5", valueInputWidth(value), valueInputProps?.className)} /> : null}
    </div>
  </FileSheetControlRow>;
}

// An empty or info line. The one style for every in-sheet message.
export function FileSheetStatusText({ children, className }) {
  return (
    <p className={cn(FILE_SHEET_STATUS_TEXT_CLASSES, className)}>
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

export function FileSheetFieldGrid({ columns = 2, children, className, ...props }) {
  return (
    <div
      {...props}
      className={cn("grid gap-1 px-2", className)}
      style={{ gridTemplateColumns: typeof columns === "number" ? `repeat(${columns}, minmax(0, 1fr))` : columns }}
    >
      {children}
    </div>
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
