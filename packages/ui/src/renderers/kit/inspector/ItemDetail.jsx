import { Check, Copy } from "lucide-react";
import { useI18n } from "@cad/ui/i18n";
import { cn } from "@cad/ui/utils";
import { useCopyFlash } from "./copyFlash.js";
import { useInspect } from "./inspect.js";
import { InfoRow, MonoValue } from "./referenceRows.jsx";

const EMPTY = Object.freeze([]);
const copyText = copy => (typeof copy === "function" ? copy() : copy);

// Its heading: its name, and at the row's right end the icon that copies its reference (the whole row is
// that one button, as it always was: the name copies too).
function Head({ item, data, copy }) {
  const { t } = useI18n();
  const flash = useCopyFlash();
  const copyable = Boolean(copy) && flash.canCopy;
  const Icon = flash.copied ? Check : Copy;
  const marks = { [`data-${data}-detail-head`]: item.id };
  const label = <span className="min-w-0 truncate">{item.title}</span>;
  return copyable ? <button type="button" aria-label={t("chip.copyReference", { name: item.title })} data-copied={flash.copied ? "" : undefined}
    onClick={() => void flash.copy(copyText(copy))} {...marks} data-detail-head=""
    className="group/title flex h-control w-full min-w-0 cursor-pointer items-center justify-between gap-2 rounded-sm text-left font-medium text-foreground outline-none focus-visible:ring-2 focus-visible:ring-ring/45">
    {label}
    <Icon className={cn("size-3 shrink-0", flash.copied ? "text-foreground" : "text-muted-foreground group-hover/title:text-foreground")} aria-hidden="true" />
  </button> : <h3 className="flex h-control min-w-0 items-center font-medium text-foreground" {...marks} data-detail-head="">{label}</h3>;
}

/**
 * What a pick is, in a Quick Edit chip's card (`ReferenceChips.jsx`), the one place a pick is read in
 * detail, from the view's description of it (`inspect.js`'s `DetailItem`): the thing in focus alone, never
 * what it holds or is connected to (the view's panel's lists are the hierarchy). Its name, the heading,
 * with the copy of its reference at the row's right end; then its few key facts as one grid: muted labels in
 * a fixed first column, values left-aligned in the second in tabular figures, every row 28px, 16px in and
 * 8px above and below, in the panel's one text size (12px; a phone's 14px).
 *
 * @param {{ item: import("./inspect.js").DetailItem, copy?: string | (() => string) | null }} props
 */
export default function ItemDetail({ item, copy = null }) {
  const data = useInspect()?.data || "item";
  const facts = item.facts || EMPTY;
  return <section aria-label={item.title} className="flex min-w-0 flex-col px-4 py-2 text-ui" data-detail-card="" {...{ [`data-${data}-detail`]: item.id }}>
    <Head item={item} data={data} copy={copy} />
    {facts.length ? <dl className="grid min-w-0 grid-cols-[4.5rem_minmax(0,1fr)] gap-x-2" data-detail-facts="">
      {facts.map(fact => <InfoRow key={fact.label} label={fact.label} title={fact.title} copy={fact.copy}>
        {typeof fact.value === "string" || typeof fact.value === "number" ? <MonoValue>{fact.value}</MonoValue> : fact.value}
      </InfoRow>)}
    </dl> : null}
  </section>;
}
