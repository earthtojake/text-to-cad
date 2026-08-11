import { ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/ui/utils";
import EntryIcon from "./EntryIcon";
import { entrySourceFormat } from "cadjs/lib/fileFormats";
import {
  renderCapabilities,
  renderFormatLabel,
  VIEWPORT_CONTENT
} from "cadjs/lib/renderCapabilities";
import {
  fileKey,
  sidebarLabelForEntry
} from "@/workbench/sidebar";

const MAX_HOME_OPTIONS = 6;

const HOME_GROUP_ORDER = ["assembly", "step", "dxf", "implicit", "robot", "mesh"];

function homeGroupForEntry(entry) {
  if (entry?.kind === "assembly") {
    return "assembly";
  }
  const capabilities = renderCapabilities(entrySourceFormat(entry));
  if (capabilities.content === VIEWPORT_CONTENT.ROBOT || entry?.kind === "srdf") {
    return "robot";
  }
  return capabilities.sheetKind;
}

// The registry already names every format for the UI; this only adds the two labels that
// come from the ENTRY rather than its format.
function formatLabelForEntry(entry, sourceFormat) {
  if (entry?.kind === "assembly") {
    return "Assembly";
  }
  if (entry?.kind === "srdf") {
    return "SRDF";
  }
  return renderFormatLabel(sourceFormat) || "STEP";
}

function pathLabelForEntry(entry) {
  return String(entry?.file || "").trim();
}

function compareEntryLabels(a, b) {
  return sidebarLabelForEntry(a).localeCompare(sidebarLabelForEntry(b), undefined, {
    numeric: true,
    sensitivity: "base"
  });
}

function addHomeEntry(result, seenKeys, entry) {
  const key = fileKey(entry);
  if (!key || seenKeys.has(key)) {
    return;
  }
  seenKeys.add(key);
  result.push(entry);
}

export function selectHomeEntries(entries) {
  const sortedEntries = [...(Array.isArray(entries) ? entries : [])].sort(compareEntryLabels);
  const result = [];
  const seenKeys = new Set();
  // One representative per SHEET KIND, in this order — a sampler of what the catalog holds.
  // Sheet kinds are the registry's own vocabulary, so a new format joins the home screen by
  // declaring a row; "assembly" and "robot" are the two groups that are not one.
  for (const group of HOME_GROUP_ORDER) {
    const match = sortedEntries.find((entry) => homeGroupForEntry(entry) === group);
    addHomeEntry(result, seenKeys, match);
  }

  for (const entry of sortedEntries) {
    if (result.length >= MAX_HOME_OPTIONS) {
      break;
    }
    addHomeEntry(result, seenKeys, entry);
  }

  return result.slice(0, MAX_HOME_OPTIONS);
}

export default function CadWorkspaceHome({
  entries,
  onSelectEntry,
  catalogHydrated = false,
  catalogRefreshing = false,
  catalogError = ""
}) {
  const homeEntries = selectHomeEntries(entries);
  const hasEntries = homeEntries.length > 0;
  const catalogErrorMessage = String(catalogError || "").trim();
  const catalogLoading = !catalogHydrated || (catalogRefreshing && !hasEntries);
  const heading = "Select a file";

  return (
    <div className="pointer-events-none absolute inset-0 z-20 flex min-w-0 items-center justify-center px-4 py-6">
      <section
        className="cad-glass-popover pointer-events-auto w-full max-w-2xl overflow-hidden rounded-md border border-sidebar-border text-popover-foreground shadow-xl shadow-black/10"
        aria-label="CAD Viewer home"
      >
        <div className="border-b border-sidebar-border px-5 py-4 sm:px-6">
          <h1 className="text-lg font-medium leading-6 text-foreground sm:text-xl">
            {heading}
          </h1>
        </div>

        <div className="divide-y divide-sidebar-border/70">
          {hasEntries ? homeEntries.map((entry) => {
            const key = fileKey(entry);
            const sourceFormat = entrySourceFormat(entry);
            const label = sidebarLabelForEntry(entry) || key;
            const pathLabel = pathLabelForEntry(entry);
            const formatLabel = formatLabelForEntry(entry, sourceFormat);

            return (
              <Button
                key={key}
                type="button"
                variant="ghost"
                className="group h-auto w-full justify-start rounded-none px-5 py-3 text-left hover:bg-sidebar-accent/80 focus-visible:ring-inset has-[>svg]:px-5 sm:px-6 sm:has-[>svg]:px-6"
                onClick={() => {
                  if (key && typeof onSelectEntry === "function") {
                    onSelectEntry(key);
                  }
                }}
                title={pathLabel || label}
              >
                <EntryIcon
                  entry={entry}
                  sourceFormat={sourceFormat}
                  className="size-4 shrink-0 text-muted-foreground group-hover:text-foreground"
                />
                <span className="min-w-0 flex-1">
                  <span className="block min-w-0 truncate text-sm font-medium text-foreground">
                    {label}
                  </span>
                  {pathLabel ? (
                    <span className="mt-0.5 block min-w-0 truncate text-[11px] font-normal text-muted-foreground">
                      {pathLabel}
                    </span>
                  ) : null}
                </span>
                <span
                  className={cn(
                    "shrink-0 rounded-md border border-sidebar-border px-1.5 py-0.5 text-[10px] font-semibold uppercase leading-none text-muted-foreground",
                    "max-sm:hidden"
                  )}
                >
                  {formatLabel}
                </span>
                <ChevronRight className="size-4 shrink-0 text-muted-foreground transition-transform group-hover:translate-x-0.5 group-hover:text-foreground" aria-hidden="true" />
              </Button>
            );
          }) : catalogErrorMessage ? (
            <p className="break-words px-5 py-5 text-sm text-muted-foreground sm:px-6" role="status">
              CAD catalog unavailable: {catalogErrorMessage}
            </p>
          ) : catalogLoading ? (
            <p className="px-5 py-5 text-sm text-muted-foreground sm:px-6" role="status">
              Loading CAD catalog...
            </p>
          ) : (
            <p className="px-5 py-5 text-sm text-muted-foreground sm:px-6">
              No CAD entries found.
            </p>
          )}
        </div>
      </section>
    </div>
  );
}
