/**
 * The card-grouped row: title and one-line description on the left, the
 * control on the right (plan §2, Codex settings).
 *
 * Every settings page is built from these, so the pages stay declarative, a new
 * page cannot invent its own row spacing, and search (`./search.tsx`) has one
 * place to hook into rather than seven.
 */
import { useEffect, useId } from "react";
import { ChevronRight, Folder } from "lucide-react";
import { cn } from "cn";

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
  const { anyMatched, report } = useMatchSet();
  const hidden = query !== "" && !anyMatched;

  useEffect(() => {
    reportSection(id, !hidden);
  }, [reportSection, id, hidden]);

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
  keywords,
  control,
  children,
}: {
  title: string;
  description?: string;
  /** Words that should find this row without being printed on it. */
  keywords?: string;
  /** Toggle, select, segmented control, field or button. */
  control?: React.ReactNode;
  /** Rendered under the row, full width — an editor, a log, a preview. */
  children?: React.ReactNode;
}) {
  const matched = useRowMatch(title, description, keywords);
  if (!matched) {
    return null;
  }
  return (
    <div className="px-4 py-3">
      <div className="flex items-center justify-between gap-6">
        <div className="min-w-0">
          <p className="text-sm">{title}</p>
          {description ? (
            <p className="mt-0.5 text-xs leading-snug text-muted-foreground">{description}</p>
          ) : null}
        </div>
        {control ? <div className="flex shrink-0 items-center gap-2">{control}</div> : null}
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
      control={
        <Switch
          aria-label={title}
          checked={checked}
          disabled={disabled}
          onCheckedChange={onChange}
        />
      }
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
  children,
}: {
  title: string;
  description?: string;
  keywords?: string;
  value: T;
  options: readonly { value: T; label: string }[];
  onChange: (value: T) => void;
  width?: string;
  children?: React.ReactNode;
}) {
  return (
    <SettingRow
      control={
        <Select onValueChange={(next) => onChange(next as T)} value={value}>
          <SelectTrigger aria-label={title} className={width} size="sm">
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
      }
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

/** A row whose control is a text field. */
export function TextRow({
  title,
  description,
  keywords,
  value,
  placeholder,
  onChange,
  width = "w-[240px]",
  type = "text",
}: {
  title: string;
  description?: string;
  keywords?: string;
  value: string;
  placeholder?: string;
  onChange: (value: string) => void;
  width?: string;
  type?: "text" | "number";
}) {
  return (
    <SettingRow
      control={
        <Input
          aria-label={title}
          className={cn("h-8", width)}
          onChange={(event) => onChange(event.target.value)}
          placeholder={placeholder}
          type={type}
          value={value}
        />
      }
      description={description}
      keywords={keywords}
      title={title}
    />
  );
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
}) {
  return (
    <SettingRow
      control={
        <>
          <span
            className={cn(
              "max-w-[260px] truncate text-xs",
              value ? "text-foreground" : "text-muted-foreground",
            )}
            data-selectable
            title={value ?? placeholder}
          >
            {value ?? placeholder}
          </span>
          <Button className="h-8 gap-1.5" onClick={onChoose} size="sm" variant="secondary">
            <Folder className="size-3.5" />
            {chooseLabel}
          </Button>
          {onClear && value ? (
            <Button className="h-8" onClick={onClear} size="sm" variant="ghost">
              Reset
            </Button>
          ) : null}
        </>
      }
      description={description}
      keywords={keywords}
      title={title}
    />
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
      control={
        <Button
          className="h-8 gap-1"
          disabled={disabled}
          onClick={onClick}
          size="sm"
          variant={variant}
        >
          {label}
          {chevron ? <ChevronRight className="size-3.5" /> : null}
        </Button>
      }
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
