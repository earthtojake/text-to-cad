import {
  Bot,
  Boxes,
  ChevronRight,
  Code,
  Cuboid,
  DraftingCompass,
  FileBox,
  FolderOpen,
  Layers3,
  Package,
  Route
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/ui/utils";
import { RENDER_FORMAT } from "@/workbench/constants";
import {
  entrySourceFormat,
  isMeshRenderFormat,
  isRobotRenderFormat
} from "cadjs/lib/fileFormats";
import {
  ENTRY_ICON_KIND,
  entryIconKind
} from "@/workbench/entryIconKind";
import {
  fileKey,
  sidebarLabelForEntry
} from "@/workbench/sidebar";

const MAX_HOME_OPTIONS = 6;

const ENTRY_ICON_COMPONENTS = {
  [ENTRY_ICON_KIND.ASSEMBLY]: Boxes,
  [ENTRY_ICON_KIND.DXF]: DraftingCompass,
  [ENTRY_ICON_KIND.GCODE]: Route,
  [ENTRY_ICON_KIND.IMPLICIT]: Code,
  [ENTRY_ICON_KIND.ROBOT]: Bot,
  [ENTRY_ICON_KIND.STEP_PART]: Package,
  [ENTRY_ICON_KIND.STL_MESH]: Cuboid,
  [ENTRY_ICON_KIND.THREE_MF_MESH]: Layers3,
  [ENTRY_ICON_KIND.GLB_MESH]: FileBox
};

function iconForEntry(entry, sourceFormat) {
  return ENTRY_ICON_COMPONENTS[entryIconKind(entry, { sourceFormat })] || Package;
}

function formatLabelForEntry(entry, sourceFormat) {
  if (entry?.kind === "assembly") {
    return "Assembly";
  }
  if (sourceFormat === RENDER_FORMAT.DXF) {
    return "DXF";
  }
  if (sourceFormat === RENDER_FORMAT.GCODE) {
    return "G-code";
  }
  if (sourceFormat === RENDER_FORMAT.IMPLICIT) {
    return "Implicit";
  }
  if (entry?.kind === "srdf") {
    return "SRDF";
  }
  if (sourceFormat === RENDER_FORMAT.URDF) {
    return "URDF";
  }
  if (sourceFormat === RENDER_FORMAT.SDF) {
    return "SDF";
  }
  if (isMeshRenderFormat(sourceFormat)) {
    return sourceFormat.toUpperCase();
  }
  return "STEP";
}

function pathLabelForEntry(entry) {
  return String(entry?.file || "").trim();
}

function directoryLabelForOption(option) {
  const rootName = String(option?.rootName || "").trim();
  if (rootName) {
    return rootName;
  }
  const pathLabel = String(option?.rootPath || option?.dir || "").trim().replace(/\\/g, "/").replace(/\/+$/g, "");
  return pathLabel.split("/").filter(Boolean).pop() || pathLabel || "Directory";
}

function directoryPathLabelForOption(option) {
  return String(option?.rootPath || option?.dir || "").trim();
}

function normalizeDirectoryOptions(options) {
  const seen = new Set();
  const result = [];
  for (const option of Array.isArray(options) ? options : []) {
    const dir = String(option?.dir || "").trim();
    const rootPath = String(option?.rootPath || "").trim();
    const key = rootPath || dir;
    if (!dir || !key || seen.has(key)) {
      continue;
    }
    seen.add(key);
    result.push({
      dir,
      rootPath,
      rootName: String(option?.rootName || "").trim()
    });
  }
  return result;
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
  const groups = [
    (entry) => entry?.kind === "assembly",
    (entry) => entrySourceFormat(entry) === RENDER_FORMAT.STEP && entry?.kind !== "assembly",
    (entry) => entrySourceFormat(entry) === RENDER_FORMAT.DXF,
    (entry) => entrySourceFormat(entry) === RENDER_FORMAT.GCODE,
    (entry) => entrySourceFormat(entry) === RENDER_FORMAT.IMPLICIT,
    (entry) => isRobotRenderFormat(entrySourceFormat(entry)) || entry?.kind === "srdf",
    (entry) => isMeshRenderFormat(entrySourceFormat(entry))
  ];

  for (const matchesGroup of groups) {
    const match = sortedEntries.find((entry) => matchesGroup(entry));
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
  catalogError = "",
  directorySelectionActive = false,
  directoryOptions = [],
  onSelectDirectory
}) {
  const homeEntries = selectHomeEntries(entries);
  const normalizedDirectoryOptions = normalizeDirectoryOptions(directoryOptions);
  const hasEntries = homeEntries.length > 0;
  const hasDirectoryOptions = normalizedDirectoryOptions.length > 0;
  const catalogErrorMessage = String(catalogError || "").trim();
  const catalogLoading = !catalogHydrated || (catalogRefreshing && !hasEntries);
  const heading = directorySelectionActive
    ? "Select a directory"
    : "Select a file";

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
          {directorySelectionActive ? (
            hasDirectoryOptions ? normalizedDirectoryOptions.map((option) => {
              const label = directoryLabelForOption(option);
              const pathLabel = directoryPathLabelForOption(option);

              return (
                <Button
                  key={option.rootPath || option.dir}
                  type="button"
                  variant="ghost"
                  className="group h-auto w-full justify-start rounded-none px-5 py-3 text-left hover:bg-sidebar-accent/80 focus-visible:ring-inset has-[>svg]:px-5 sm:px-6 sm:has-[>svg]:px-6"
                  onClick={() => {
                    if (typeof onSelectDirectory === "function") {
                      onSelectDirectory(option.dir);
                    }
                  }}
                  title={pathLabel || label}
                >
                  <FolderOpen className="size-4 shrink-0 text-muted-foreground group-hover:text-foreground" aria-hidden="true" />
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
                    Directory
                  </span>
                  <ChevronRight className="size-4 shrink-0 text-muted-foreground transition-transform group-hover:translate-x-0.5 group-hover:text-foreground" aria-hidden="true" />
                </Button>
              );
            }) : (
              <p className="px-5 py-5 text-sm text-muted-foreground sm:px-6">
                No active directories found.
              </p>
            )
          ) : hasEntries ? homeEntries.map((entry) => {
            const key = fileKey(entry);
            const sourceFormat = entrySourceFormat(entry);
            const EntryIcon = iconForEntry(entry, sourceFormat);
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
                <EntryIcon className="size-4 shrink-0 text-muted-foreground group-hover:text-foreground" aria-hidden="true" />
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
