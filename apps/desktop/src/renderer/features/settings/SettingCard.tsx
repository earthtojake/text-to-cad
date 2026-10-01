/**
 * The card-grouped row: title and one-line description on the left, the
 * control on the right (plan §2, Codex settings).
 *
 * Every settings page is built from these, so the pages stay declarative, a new
 * page cannot invent its own row spacing, and search (`./search.tsx`) has one
 * place to hook into rather than seven.
 */
import { useCallback, useEffect, useId, useRef, useState } from "react";
import { ChevronRight, Folder } from "lucide-react";
import { toast } from "sonner";
import { cn } from "cn";
import { TooltipHint } from "@text-to-cad/ui/primitives/tooltip";

import { Button } from "@renderer/components/ui/button";
import { Input } from "@renderer/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@renderer/components/ui/select";
import { Switch } from "@renderer/components/ui/switch";
import {
  CardMatchProvider,
  matchesQuery,
  useCardReport,
  useMatchSet,
  useSectionReport,
  useSettingsQuery,
} from "@renderer/features/settings/search";

export function SettingCard({
  title,
  children,
  className,
}: {
  /** Optional plain heading above the card. */
  title?: string;
  children: React.ReactNode;
  className?: string;
}) {
  const id = useId();
  const query = useSettingsQuery();
  const { report: reportSection } = useSectionReport();
  const { anyMatched, matchedCount, report } = useMatchSet();
  const hidden = query !== "" && !anyMatched;

  useEffect(() => {
    reportSection(id, hidden ? 0 : matchedCount);
    // Withdrawn when the card goes: clearing the box unmounts every searched
    // page, and the next search mounts its cards under new ids — a match left
    // behind would keep a page in the nav that has nothing to show.
    return () => reportSection(id, 0);
  }, [reportSection, id, hidden, matchedCount]);

  return (
    <CardMatchProvider report={report}>
      {/* Hidden rather than unmounted: a card that removed its rows from the
          tree would stop hearing whether they match, and could never come
          back when the query changed. */}
      <section className={cn("mb-6", className)} hidden={hidden}>
        {title ? (
          <h2 className="mb-2 px-1 text-[13px] font-medium text-muted-foreground">{title}</h2>
        ) : null}
        <div className="divide-y overflow-hidden rounded-xl border bg-card">{children}</div>
      </section>
    </CardMatchProvider>
  );
}

/**
 * One row. Renders nothing when the active query does not match its text —
 * `null`, not an unmount, so it keeps reporting and reappears when the query
 * changes.
 */
export function SettingRow({
  title,
  description,
  live,
  keywords,
  control,
  children,
}: {
  title: string;
  description?: string;
  /** The description is a status that changes under the person's hands: announced when it does. */
  live?: boolean;
  /** Words that should find this row without being printed on it. */
  keywords?: string;
  /**
   * Toggle, select, segmented control, field or button. A function gets the id of the
   * description (or undefined when the row has none) to hang on the control as
   * `aria-describedby`, so a screen reader reads the sentence with the control rather than
   * beside it.
   */
  control?: React.ReactNode | ((describedBy: string | undefined) => React.ReactNode);
  /** Rendered under the row, full width — an editor, a log, a preview. */
  children?: React.ReactNode;
}) {
  const matched = useRowMatch(title, description, keywords);
  const descriptionId = useId();
  if (!matched) {
    return null;
  }
  const describedBy = description ? descriptionId : undefined;
  return (
    <div className="px-4 py-3">
      <div className="flex items-center justify-between gap-6">
        <div className="min-w-0">
          <p className="text-[13px] leading-5">{title}</p>
          {description ? (
            <p
              className="mt-0.5 text-xs leading-snug text-muted-foreground"
              id={descriptionId}
              role={live ? "status" : undefined}
            >
              {description}
            </p>
          ) : null}
        </div>
        {control ? (
          <div className="flex shrink-0 items-center gap-2">{typeof control === "function" ? control(describedBy) : control}</div>
        ) : null}
      </div>
      {children ? <div className="mt-3">{children}</div> : null}
    </div>
  );
}

/** Registers a row with its card and answers whether the query matches it. */
export function useRowMatch(...fields: (string | undefined)[]): boolean {
  const id = useId();
  const query = useSettingsQuery();
  const report = useCardReport();
  const matched = matchesQuery(query, ...fields);

  useEffect(() => {
    report(id, matched);
    return () => report(id, false);
  }, [report, id, matched]);

  return matched;
}

/* -------------------------------------------------------------------------- */
/* Controls                                                                    */
/* -------------------------------------------------------------------------- */

/** A row whose control is a switch. */
export function SwitchRow({
  title,
  description,
  keywords,
  checked,
  disabled,
  onChange,
  children,
}: {
  title: string;
  description?: string;
  keywords?: string;
  checked: boolean;
  disabled?: boolean;
  onChange: (checked: boolean) => void;
  children?: React.ReactNode;
}) {
  return (
    <SettingRow
      control={(describedBy) => (
        <Switch
          aria-describedby={describedBy}
          aria-label={title}
          // The vendored switch's off track is `bg-input` with a transparent
          // border, which on the light theme's white card is next to
          // invisible. An off switch still has to read as a switch.
          className="data-[state=unchecked]:border-foreground/25"
          checked={checked}
          disabled={disabled}
          onCheckedChange={onChange}
        />
      )}
      description={description}
      keywords={keywords}
      title={title}
    >
      {children}
    </SettingRow>
  );
}

/** A row whose control is a select. */
export function SelectRow<T extends string>({
  title,
  description,
  keywords,
  value,
  options,
  onChange,
  width = "w-[200px]",
  disabled = false,
  children,
}: {
  title: string;
  description?: string;
  keywords?: string;
  value: T;
  options: readonly { value: T; label: string }[];
  onChange: (value: T) => void;
  width?: string;
  /** Off while another setting makes this one mean nothing; the description says which. */
  disabled?: boolean;
  children?: React.ReactNode;
}) {
  return (
    <SettingRow
      control={(describedBy) => (
        <Select disabled={disabled} onValueChange={(next) => onChange(next as T)} value={value}>
          <SelectTrigger aria-describedby={describedBy} aria-label={title} className={width} size="sm">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {options.map((option) => (
              <SelectItem key={option.value} value={option.value}>
                {option.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      )}
      description={description}
      keywords={
        // The option labels are part of what the row is about: someone
        // searching "worktree" should find the git-mode row.
        [keywords, ...options.map((option) => option.label)].filter(Boolean).join(" ")
      }
      title={title}
    >
      {children}
    </SettingRow>
  );
}

/**
 * A text control's own copy of what is being typed, handed to the store on
 * blur and Enter rather than on every keystroke.
 *
 * Per keystroke, each character was a `settings.set` and a `settings_changed`
 * event, and the answers came back late: the one for "a" landed after "ab"
 * had been typed and put "a" back, the caret jumped to the end, and the next
 * key went in after it. While the field is being edited the store's value is
 * not let in; once the edit is over, the store's value is the field's again.
 * A draft still open when the row unmounts — Settings closed mid-sentence —
 * is committed then.
 *
 * `same` says when the store's value is the draft, in the store's own terms:
 * a field whose text normalises on the way in (comments and malformed lines
 * dropped) would otherwise be rewritten to the normal form the moment its
 * edit committed, erasing what the person typed.
 */
export function useDraft(
  value: string,
  commit: (value: string) => void,
  same: (draft: string, value: string) => boolean = (draft, next) => draft === next,
) {
  const [draft, setDraft] = useState(value);
  const editing = useRef(false);
  const latest = useRef({ draft: value, committed: value, commit, same });
  useEffect(() => {
    latest.current.commit = commit;
    latest.current.same = same;
  }, [commit, same]);

  useEffect(() => {
    if (!editing.current && !latest.current.same(latest.current.draft, value)) {
      latest.current.draft = value;
      latest.current.committed = value;
      setDraft(value);
    }
  }, [value]);

  const flush = useCallback(() => {
    const current = latest.current;
    if (current.draft !== current.committed) {
      current.committed = current.draft;
      current.commit(current.draft);
    }
  }, []);
  useEffect(() => flush, [flush]);

  return {
    value: draft,
    onChange: (next: string) => {
      editing.current = true;
      latest.current.draft = next;
      setDraft(next);
    },
    onFocus: () => {
      editing.current = true;
    },
    onBlur: () => {
      editing.current = false;
      flush();
    },
    flush,
  };
}

/**
 * A row whose control is a text field. `onChange` hears a finished edit — on
 * blur or Enter (`useDraft`) — not each keystroke.
 */
export function TextRow({
  title,
  description,
  keywords,
  value,
  placeholder,
  onChange,
  width = "w-[240px]",
  type = "text",
  problem,
  note,
  warning,
}: {
  title: string;
  description?: string;
  keywords?: string;
  value: string;
  placeholder?: string;
  onChange: (value: string) => void;
  width?: string;
  type?: "text" | "number";
  /**
   * Why a value would be refused, or null. A refused value is shown with its
   * reason under the row and never written — main would refuse the patch, and
   * the field would be left showing a value nothing stored.
   */
  problem?: (value: string) => string | null;
  /** Said under the row while the field shows no problem of its own. */
  note?: React.ReactNode;
  /**
   * Drawn under the row in place of `note`, as it is given — the caller's own
   * alert — while the field shows no problem of its own: something wrong with
   * what is stored rather than with what is typed.
   */
  warning?: React.ReactNode;
}) {
  const draft = useDraft(value, (next) => {
    if (!problem?.(next)) {
      onChange(next);
    }
  });
  const problemId = useId();
  const refused = problem?.(draft.value) ?? null;
  // A refused value left in the field when the row goes (Settings closed, the
  // page changed) was never written; the alert under the row goes with it, so
  // a toast says so instead of the value vanishing without a word.
  const left = useRef<{ value: string; reason: string } | null>(null);
  useEffect(() => {
    left.current = refused ? { value: draft.value, reason: refused } : null;
  });
  useEffect(
    () => () => {
      if (left.current) {
        toast.error(`${title} “${left.current.value}” was not saved`, { description: left.current.reason });
      }
    },
    [title],
  );
  return (
    <SettingRow
      control={(describedBy) => (
        <Input
          aria-describedby={[refused ? problemId : undefined, describedBy].filter(Boolean).join(" ") || undefined}
          aria-invalid={refused ? true : undefined}
          aria-label={title}
          className={cn("h-8", width)}
          onBlur={draft.onBlur}
          onChange={(event) => draft.onChange(event.target.value)}
          onFocus={draft.onFocus}
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              draft.flush();
            }
          }}
          placeholder={placeholder}
          type={type}
          value={draft.value}
        />
      )}
      description={description}
      keywords={keywords}
      title={title}
    >
      {refused ? (
        <p className="text-xs text-destructive" id={problemId} role="alert">
          {refused}
        </p>
      ) : warning ? (
        warning
      ) : note ? (
        <p className="text-xs text-muted-foreground">{note}</p>
      ) : null}
    </SettingRow>
  );
}

/** "Default project folder" → "default project folder", but "Git root" keeps its capital. */
function lowerFirst(text: string): string {
  return /^[A-Z][a-z]/.test(text) ? text.charAt(0).toLowerCase() + text.slice(1) : text;
}

/**
 * A row whose value is a path on disk: the path, a chooser, and a way back to
 * the default.
 *
 * The field is read-only on purpose. A path typed by hand is a path with a
 * typo, and the only thing the app can do with one is fail later, somewhere
 * else; the chooser is the native dialog that cannot produce a path that does
 * not exist.
 */
export function PathRow({
  title,
  description,
  keywords,
  value,
  placeholder,
  onChoose,
  onClear,
  chooseLabel = "Choose…",
  note,
}: {
  title: string;
  description?: string;
  keywords?: string;
  value: string | null;
  /** Shown greyed when nothing is set — usually the default that applies. */
  placeholder: string;
  onChoose: () => void;
  onClear?: () => void;
  chooseLabel?: string;
  /** A quiet line under the row — the stored folder is gone. */
  note?: string;
}) {
  return (
    <SettingRow
      control={(describedBy) => (
        <>
          <TooltipHint content={value ?? placeholder} overflowOnly>
            <span
              className={cn(
                "max-w-[260px] truncate text-xs",
                value ? "text-foreground" : "text-muted-foreground",
              )}
              data-selectable
            >
              {value ?? placeholder}
            </span>
          </TooltipHint>
          {/* Two rows of buttons named "Choose…" and "Reset" are a list a screen reader cannot
              tell apart: the row's title finishes each name. */}
          <Button
            aria-describedby={describedBy}
            aria-label={`${chooseLabel.replace(/…$/, "")} ${lowerFirst(title)}`}
            className="h-8 gap-1.5"
            onClick={onChoose}
            size="sm"
            variant="secondary"
          >
            <Folder className="size-3.5" />
            {chooseLabel}
          </Button>
          {onClear && value ? (
            <Button aria-describedby={describedBy} aria-label={`Reset ${lowerFirst(title)}`} className="h-8" onClick={onClear} size="sm" variant="ghost">
              Reset
            </Button>
          ) : null}
        </>
      )}
      description={description}
      keywords={keywords}
      title={title}
    >
      {note ? <p className="text-xs text-muted-foreground">{note}</p> : null}
    </SettingRow>
  );
}

/** A row whose control is a button that opens something else. */
export function ActionRow({
  title,
  description,
  keywords,
  label,
  onClick,
  disabled,
  variant = "secondary",
  chevron,
}: {
  title: string;
  description?: string;
  keywords?: string;
  label: string;
  onClick: () => void;
  disabled?: boolean;
  variant?: "secondary" | "ghost" | "default" | "destructive";
  chevron?: boolean;
}) {
  return (
    <SettingRow
      control={(describedBy) => (
        <Button
          aria-describedby={describedBy}
          className="h-8 gap-1"
          disabled={disabled}
          onClick={onClick}
          size="sm"
          variant={variant}
        >
          {label}
          {chevron ? <ChevronRight className="size-3.5" /> : null}
        </Button>
      )}
      description={description}
      keywords={keywords}
      title={title}
    />
  );
}

/** A row that only reports a value. */
export function ValueRow({
  title,
  description,
  keywords,
  value,
  tone = "muted",
}: {
  title: string;
  description?: string;
  keywords?: string;
  value: React.ReactNode;
  tone?: "muted" | "strong";
}) {
  return (
    <SettingRow
      control={
        <span
          className={cn(
            "max-w-[280px] truncate text-sm",
            tone === "muted" ? "text-muted-foreground" : "text-foreground",
          )}
          data-selectable
        >
          {value}
        </span>
      }
      description={description}
      keywords={keywords}
      title={title}
    />
  );
}
