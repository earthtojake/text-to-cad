import {
  ArrowUpFromLine,
  Bot,
  Boxes,
  ChevronDown,
  ChevronRight,
  Code,
  Cuboid,
  DraftingCompass,
  FileBox,
  FolderOpen,
  Layers3,
  LoaderCircle,
  Package,
  Route
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger
} from "@/components/ui/collapsible";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger
} from "@/components/ui/dropdown-menu";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader as SheetHeaderPrimitive,
  SheetTitle
} from "@/components/ui/sheet";
import {
  SidebarContent,
  SidebarGroup,
  SidebarGroupContent,
  SidebarHeader,
  SidebarInput,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarMenuSub,
  SidebarMenuSubItem,
  useSidebar
} from "@/components/ui/sidebar";
import { cn } from "@/ui/utils";
import {
  ENTRY_ICON_KIND,
  entryIconKind
} from "@/workbench/entryIconKind";
import {
  entryIconStatus,
  entryStepSourceKind
} from "@/workbench/entryIconStatus";
import {
  fileKey,
  listSidebarItems,
  sidebarLabelForEntry
} from "@/workbench/sidebar";
import FileAccessContextMenu from "./FileAccessContextMenu";

const DESKTOP_FILE_VIEWER_MIN_WIDTH = 150;
const DESKTOP_FILE_VIEWER_MAX_WIDTH = "calc(100vw - 0.75rem)";
const MOBILE_FILE_VIEWER_WIDTH = "min(18rem, calc(100vw - 0.75rem))";

const ENTRY_ICON_COMPONENTS = {
  [ENTRY_ICON_KIND.LOADING]: LoaderCircle,
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

function iconForEntry(entry, sourceFormat, status) {
  return ENTRY_ICON_COMPONENTS[entryIconKind(entry, { sourceFormat, status })] || Package;
}

function FileEntryButton({
  entry,
  depth,
  selectedKey,
  onSelectEntry,
  entrySourceFormat,
  entryHasMesh,
  entryHasDxf,
  entryHasGcode,
  entryHasUrdf,
  activeGenerationFiles = [],
  activeStepArtifactGenerationFile = "",
  stepArtifactGenerationAvailable = true,
  canRevealFileAssets = false,
  canCopyFileAssetLinks = false,
  canCopyFileAssetPaths = false,
  fileAccessBusyKey = "",
  onDownloadFileAsset,
  onExportImplicitFile,
  onRevealFileAsset,
  onRevealInExplorerView,
  onCopyFileAssetReference,
  nested = false
}) {
  const { isMobile, setOpenMobile } = useSidebar();
  const key = fileKey(entry);
  const active = key === selectedKey;
  const label = sidebarLabelForEntry(entry);
  const sourceFormat = entrySourceFormat(entry);
  const status = entryIconStatus(entry, {
    sourceFormat,
    entryKey: key,
    hasMesh: entryHasMesh(entry),
    hasDxf: entryHasDxf(entry),
    hasGcode: entryHasGcode(entry),
    hasUrdf: entryHasUrdf(entry),
    activeGenerationFiles,
    activeStepArtifactGenerationFile,
    stepArtifactGenerationAvailable
  });
  const EntryIcon = iconForEntry(entry, sourceFormat, status);
  const stepSourceKind = entryStepSourceKind(entry);
  const SourceBadgeIcon = stepSourceKind === "python"
    ? Code
    : stepSourceKind === "step"
      ? ArrowUpFromLine
      : null;
  const showSourceBadge = Boolean(SourceBadgeIcon);
  const title = [
    label,
    stepSourceKind === "python" ? "Python-backed" : "",
    stepSourceKind === "step" ? "STEP-backed" : "",
    status.statusLabel,
    entry?.kind,
    String(entry?.file || "")
  ].filter(Boolean).join(" | ");

  const button = (
    <SidebarMenuButton
      type="button"
      isActive={active}
      size="sm"
      title={title}
      className={cn(
        "min-w-0 w-full justify-start"
      )}
      onClick={() => {
        onSelectEntry(key);
        if (isMobile) {
          setOpenMobile(false);
        }
      }}
      tooltip={label}
    >
      <span className="relative flex size-4 shrink-0 items-center justify-center" aria-hidden="true">
        <EntryIcon
          className={cn(
            "size-4",
            status.loading && "animate-spin"
          )}
        />
        {showSourceBadge ? (
          <span className="absolute -bottom-1 -right-1 flex size-2.5 items-center justify-center rounded-[3px] border border-sidebar bg-sidebar text-sidebar-foreground shadow-sm">
            <SourceBadgeIcon className="size-2" strokeWidth={2.5} />
          </span>
        ) : null}
      </span>
      <span className="block min-w-0 flex-1 max-w-full overflow-hidden text-ellipsis whitespace-nowrap">{label}</span>
    </SidebarMenuButton>
  );

  return (
    <FileAccessContextMenu
      entry={entry}
      canRevealFileAssets={canRevealFileAssets}
      canCopyFileAssetLinks={canCopyFileAssetLinks}
      canCopyFileAssetPaths={canCopyFileAssetPaths}
      busyKey={fileAccessBusyKey}
      onDownloadFileAsset={onDownloadFileAsset}
      onExportImplicitFile={onExportImplicitFile}
      onRevealFileAsset={onRevealFileAsset}
      onRevealInExplorerView={onRevealInExplorerView}
      onCopyFileAssetReference={onCopyFileAssetReference}
    >
      {button}
    </FileAccessContextMenu>
  );
}

function DirectoryNode({
  directory,
  depth,
  queryActive,
  expandedDirectoryIds,
  onToggleDirectory,
  selectedKey,
  onSelectEntry,
  entrySourceFormat,
  entryHasMesh,
  entryHasDxf,
  entryHasGcode,
  entryHasUrdf,
  activeGenerationFiles = [],
  activeStepArtifactGenerationFile = "",
  stepArtifactGenerationAvailable = true,
  canRevealFileAssets = false,
  canCopyFileAssetLinks = false,
  canCopyFileAssetPaths = false,
  fileAccessBusyKey = "",
  onDownloadFileAsset,
  onExportImplicitFile,
  onRevealFileAsset,
  onRevealInExplorerView,
  onCopyFileAssetReference,
  nested = false
}) {
  const expanded = queryActive || expandedDirectoryIds.has(directory.id);
  const DirectoryItem = nested ? SidebarMenuSubItem : SidebarMenuItem;

  return (
    <Collapsible asChild open={expanded}>
      <DirectoryItem className="min-w-0 w-full max-w-full">
        <CollapsibleTrigger asChild>
          <SidebarMenuButton
            type="button"
            size="sm"
            title={directory.name}
            aria-disabled={queryActive}
            className={cn(
              "group/directory min-w-0 w-full justify-start",
              queryActive && "cursor-default"
            )}
            onClick={(event) => {
              if (queryActive) {
                event.preventDefault();
                return;
              }
              onToggleDirectory(directory.id);
            }}
          >
            <ChevronRight
              className={cn(
                "transition-transform",
                expanded && "rotate-90"
              )}
              aria-hidden="true"
            />
            <span className="block min-w-0 flex-1 max-w-full overflow-hidden text-ellipsis whitespace-nowrap">{directory.name}</span>
          </SidebarMenuButton>
        </CollapsibleTrigger>

        <CollapsibleContent className="min-w-0 w-full max-w-full">
          <SidebarMenuSub className="min-w-0 w-full max-w-full">
            {listSidebarItems(directory).map((item) => {
              if (item.type === "directory") {
                return (
                  <DirectoryNode
                    key={item.key}
                    directory={item.value}
                    depth={depth + 1}
                    queryActive={queryActive}
                    expandedDirectoryIds={expandedDirectoryIds}
                    onToggleDirectory={onToggleDirectory}
                    selectedKey={selectedKey}
                    onSelectEntry={onSelectEntry}
                    entrySourceFormat={entrySourceFormat}
                    entryHasMesh={entryHasMesh}
                    entryHasDxf={entryHasDxf}
                    entryHasGcode={entryHasGcode}
                    entryHasUrdf={entryHasUrdf}
                    activeGenerationFiles={activeGenerationFiles}
                    activeStepArtifactGenerationFile={activeStepArtifactGenerationFile}
                    stepArtifactGenerationAvailable={stepArtifactGenerationAvailable}
                    canRevealFileAssets={canRevealFileAssets}
                    canCopyFileAssetLinks={canCopyFileAssetLinks}
                    canCopyFileAssetPaths={canCopyFileAssetPaths}
                    fileAccessBusyKey={fileAccessBusyKey}
                    onDownloadFileAsset={onDownloadFileAsset}
                    onExportImplicitFile={onExportImplicitFile}
                    onRevealFileAsset={onRevealFileAsset}
                    onRevealInExplorerView={onRevealInExplorerView}
                    onCopyFileAssetReference={onCopyFileAssetReference}
                    nested={true}
                  />
                );
              }
              return (
                <SidebarMenuSubItem key={item.key} className="min-w-0 w-full max-w-full">
                  <FileEntryButton
                    entry={item.value}
                    depth={depth + 1}
                    selectedKey={selectedKey}
                    onSelectEntry={onSelectEntry}
                    entrySourceFormat={entrySourceFormat}
                    entryHasMesh={entryHasMesh}
                    entryHasDxf={entryHasDxf}
                    entryHasGcode={entryHasGcode}
                    entryHasUrdf={entryHasUrdf}
                    activeGenerationFiles={activeGenerationFiles}
                    activeStepArtifactGenerationFile={activeStepArtifactGenerationFile}
                    stepArtifactGenerationAvailable={stepArtifactGenerationAvailable}
                    canRevealFileAssets={canRevealFileAssets}
                    canCopyFileAssetLinks={canCopyFileAssetLinks}
                    canCopyFileAssetPaths={canCopyFileAssetPaths}
                    fileAccessBusyKey={fileAccessBusyKey}
                    onDownloadFileAsset={onDownloadFileAsset}
                    onExportImplicitFile={onExportImplicitFile}
                    onRevealFileAsset={onRevealFileAsset}
                    onRevealInExplorerView={onRevealInExplorerView}
                    onCopyFileAssetReference={onCopyFileAssetReference}
                    nested={true}
                  />
                </SidebarMenuSubItem>
              );
            })}
          </SidebarMenuSub>
        </CollapsibleContent>
      </DirectoryItem>
    </Collapsible>
  );
}

function SidebarResizeHandle({ onStartResize }) {
  const { isMobile, state } = useSidebar();

  if (isMobile || state !== "expanded" || typeof onStartResize !== "function") {
    return null;
  }

  return (
    <Button
      type="button"
      variant="ghost"
      size="sm"
      aria-label="Resize file viewer sidebar"
      title="Resize sidebar"
      onPointerDown={onStartResize}
      className="group/sidebar-resize absolute inset-y-0 -right-1.5 z-30 flex h-auto w-3 cursor-col-resize touch-none items-stretch justify-center rounded-none px-0 py-0 hover:bg-transparent"
    >
      <span className="my-2 w-px rounded-full bg-transparent transition-colors group-hover/sidebar-resize:bg-sidebar-border group-focus-visible/sidebar-resize:bg-ring" />
    </Button>
  );
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

function DirectorySwitcher({
  directoryOptions = [],
  activeDirectory = "",
  onSelectDirectory
}) {
  const options = normalizeDirectoryOptions(directoryOptions);
  if (options.length <= 1) {
    return null;
  }

  const activeDir = String(activeDirectory || "").trim();
  const activeOption = options.find((option) => option.dir === activeDir || option.rootPath === activeDir) || options[0];
  const activeLabel = directoryLabelForOption(activeOption);
  const activePathLabel = directoryPathLabelForOption(activeOption);

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="h-7 w-full justify-between gap-2 rounded-md p-2 text-xs font-medium text-sidebar-foreground hover:bg-sidebar-accent hover:text-sidebar-accent-foreground"
          title={activePathLabel || activeLabel}
        >
          <span className="flex min-w-0 flex-1 items-center gap-2">
            <span className="flex size-4 shrink-0 items-center justify-center" aria-hidden="true">
              <FolderOpen className="size-4 text-muted-foreground" />
            </span>
            <span className="min-w-0 truncate">{activeLabel}</span>
          </span>
          <ChevronDown className="size-3.5 shrink-0 text-muted-foreground" aria-hidden="true" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="w-[--radix-dropdown-menu-trigger-width] max-w-[min(28rem,calc(100vw-1rem))]">
        {options.map((option) => {
          const label = directoryLabelForOption(option);
          const pathLabel = directoryPathLabelForOption(option);
          const active = option.dir === activeOption.dir || option.rootPath === activeOption.rootPath;
          return (
            <DropdownMenuItem
              key={option.rootPath || option.dir}
              className={cn(
                "min-w-0 items-start gap-2 text-xs",
                active && "bg-accent text-accent-foreground"
              )}
              onSelect={() => {
                if (typeof onSelectDirectory === "function" && option.dir !== activeOption.dir) {
                  onSelectDirectory(option.dir);
                }
              }}
              title={pathLabel || label}
            >
              <FolderOpen className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
              <span className="min-w-0 flex-1">
                <span className="block truncate font-medium">{label}</span>
                {pathLabel ? (
                  <span className="mt-0.5 block truncate text-[11px] text-muted-foreground">{pathLabel}</span>
                ) : null}
              </span>
            </DropdownMenuItem>
          );
        })}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function FileViewerContents({
  query,
  onQueryChange,
  filteredEntries,
  catalogEntries,
  filteredEntriesTree,
  selectedKey,
  expandedDirectoryIds,
  onToggleDirectory,
  onSelectEntry,
  entrySourceFormat,
  entryHasMesh,
  entryHasDxf,
  entryHasGcode,
  entryHasUrdf,
  activeGenerationFiles = [],
  activeStepArtifactGenerationFile = "",
  stepArtifactGenerationAvailable = true,
  canRevealFileAssets = false,
  canCopyFileAssetLinks = false,
  canCopyFileAssetPaths = false,
  fileAccessBusyKey = "",
  onDownloadFileAsset,
  onExportImplicitFile,
  onRevealFileAsset,
  onRevealInExplorerView,
  onCopyFileAssetReference,
  catalogHydrated = false,
  catalogRefreshing = false,
  catalogError = "",
  directoryOptions = [],
  activeDirectory = "",
  onSelectDirectory,
  resizable = true,
  onStartResize
}) {
  const queryActive = query.trim().length > 0;
  const hasMatches = filteredEntries.length > 0;
  const hasEntries = catalogEntries.length > 0;
  const catalogErrorMessage = String(catalogError || "").trim();
  const catalogLoading = !catalogHydrated || (catalogRefreshing && !hasEntries);

  return (
    <>
      <SidebarHeader className="gap-2">
        <DirectorySwitcher
          directoryOptions={directoryOptions}
          activeDirectory={activeDirectory}
          onSelectDirectory={onSelectDirectory}
        />
        <SidebarInput
          type="search"
          placeholder="Search files, ids, or paths..."
          value={query}
          onChange={(event) => onQueryChange(event.target.value)}
          aria-label="Search CAD files"
          className="h-7 text-xs md:text-xs"
        />
      </SidebarHeader>

      <SidebarContent>
        <ScrollArea className="cad-file-viewer-scroll min-h-0 min-w-0 flex-1 overflow-x-hidden" type="auto">
          <SidebarGroup>
            <SidebarGroupContent>
              {hasMatches ? (
                <SidebarMenu>
                  {listSidebarItems(filteredEntriesTree).map((item) => {
                    if (item.type === "directory") {
                      return (
                        <DirectoryNode
                          key={item.key}
                          directory={item.value}
                          depth={0}
                          queryActive={queryActive}
                          expandedDirectoryIds={expandedDirectoryIds}
                          onToggleDirectory={onToggleDirectory}
                          selectedKey={selectedKey}
                          onSelectEntry={onSelectEntry}
                          entrySourceFormat={entrySourceFormat}
                          entryHasMesh={entryHasMesh}
                          entryHasDxf={entryHasDxf}
                          entryHasGcode={entryHasGcode}
                          entryHasUrdf={entryHasUrdf}
                          activeGenerationFiles={activeGenerationFiles}
                          activeStepArtifactGenerationFile={activeStepArtifactGenerationFile}
                          stepArtifactGenerationAvailable={stepArtifactGenerationAvailable}
                          canRevealFileAssets={canRevealFileAssets}
                          canCopyFileAssetLinks={canCopyFileAssetLinks}
                          canCopyFileAssetPaths={canCopyFileAssetPaths}
                          fileAccessBusyKey={fileAccessBusyKey}
                          onDownloadFileAsset={onDownloadFileAsset}
                          onExportImplicitFile={onExportImplicitFile}
                          onRevealFileAsset={onRevealFileAsset}
                          onRevealInExplorerView={onRevealInExplorerView}
                          onCopyFileAssetReference={onCopyFileAssetReference}
                        />
                      );
                    }
                    return (
                      <SidebarMenuItem key={item.key} className="min-w-0 w-full max-w-full">
                        <FileEntryButton
                          entry={item.value}
                          depth={0}
                          selectedKey={selectedKey}
                          onSelectEntry={onSelectEntry}
                          entrySourceFormat={entrySourceFormat}
                          entryHasMesh={entryHasMesh}
                          entryHasDxf={entryHasDxf}
                          entryHasGcode={entryHasGcode}
                          entryHasUrdf={entryHasUrdf}
                          activeGenerationFiles={activeGenerationFiles}
                          activeStepArtifactGenerationFile={activeStepArtifactGenerationFile}
                          stepArtifactGenerationAvailable={stepArtifactGenerationAvailable}
                          canRevealFileAssets={canRevealFileAssets}
                          canCopyFileAssetLinks={canCopyFileAssetLinks}
                          canCopyFileAssetPaths={canCopyFileAssetPaths}
                          fileAccessBusyKey={fileAccessBusyKey}
                          onDownloadFileAsset={onDownloadFileAsset}
                          onExportImplicitFile={onExportImplicitFile}
                          onRevealFileAsset={onRevealFileAsset}
                          onRevealInExplorerView={onRevealInExplorerView}
                          onCopyFileAssetReference={onCopyFileAssetReference}
                        />
                      </SidebarMenuItem>
                    );
                  })}
                </SidebarMenu>
              ) : catalogErrorMessage && !hasEntries ? (
                <p className="px-2 py-3 text-xs text-muted-foreground">CAD catalog unavailable: {catalogErrorMessage}</p>
              ) : catalogLoading ? (
                <p className="px-2 py-3 text-xs text-muted-foreground">Loading CAD catalog...</p>
              ) : hasEntries ? (
                <p className="px-2 py-3 text-xs text-muted-foreground">No CAD entries match this filter.</p>
              ) : (
                <p className="px-2 py-3 text-xs text-muted-foreground">No CAD entries found.</p>
              )}
            </SidebarGroupContent>
          </SidebarGroup>
        </ScrollArea>
      </SidebarContent>
      <SidebarResizeHandle onStartResize={resizable ? onStartResize : null} />
    </>
  );
}

export default function FileViewerSidebar({
  previewMode,
  query,
  onQueryChange,
  filteredEntries,
  catalogEntries,
  filteredEntriesTree,
  selectedKey,
  expandedDirectoryIds,
  onToggleDirectory,
  onSelectEntry,
  entrySourceFormat,
  entryHasMesh,
  entryHasDxf,
  entryHasGcode,
  entryHasUrdf,
  activeGenerationFiles = [],
  activeStepArtifactGenerationFile = "",
  stepArtifactGenerationAvailable = true,
  canRevealFileAssets = false,
  canCopyFileAssetLinks = false,
  canCopyFileAssetPaths = false,
  fileAccessBusyKey = "",
  onDownloadFileAsset,
  onExportImplicitFile,
  onRevealFileAsset,
  onRevealInExplorerView,
  onCopyFileAssetReference,
  catalogHydrated = false,
  catalogRefreshing = false,
  catalogError = "",
  directoryOptions = [],
  activeDirectory = "",
  onSelectDirectory,
  resizable = true,
  onStartResize
}) {
  const { isMobile, state, openMobile, setOpenMobile } = useSidebar();

  if (previewMode) {
    return null;
  }

  const content = (
    <FileViewerContents
      query={query}
      onQueryChange={onQueryChange}
      filteredEntries={filteredEntries}
      catalogEntries={catalogEntries}
      filteredEntriesTree={filteredEntriesTree}
      selectedKey={selectedKey}
      expandedDirectoryIds={expandedDirectoryIds}
      onToggleDirectory={onToggleDirectory}
      onSelectEntry={onSelectEntry}
      entrySourceFormat={entrySourceFormat}
      entryHasMesh={entryHasMesh}
      entryHasDxf={entryHasDxf}
      entryHasGcode={entryHasGcode}
      entryHasUrdf={entryHasUrdf}
      activeGenerationFiles={activeGenerationFiles}
      activeStepArtifactGenerationFile={activeStepArtifactGenerationFile}
      stepArtifactGenerationAvailable={stepArtifactGenerationAvailable}
      canRevealFileAssets={canRevealFileAssets}
      canCopyFileAssetLinks={canCopyFileAssetLinks}
      canCopyFileAssetPaths={canCopyFileAssetPaths}
      fileAccessBusyKey={fileAccessBusyKey}
      onDownloadFileAsset={onDownloadFileAsset}
      onExportImplicitFile={onExportImplicitFile}
      onRevealFileAsset={onRevealFileAsset}
      onRevealInExplorerView={onRevealInExplorerView}
      onCopyFileAssetReference={onCopyFileAssetReference}
      catalogHydrated={catalogHydrated}
      catalogRefreshing={catalogRefreshing}
      catalogError={catalogError}
      directoryOptions={directoryOptions}
      activeDirectory={activeDirectory}
      onSelectDirectory={onSelectDirectory}
      resizable={resizable}
      onStartResize={onStartResize}
    />
  );

  if (isMobile) {
    return (
      <Sheet open={openMobile} onOpenChange={setOpenMobile}>
        <SheetContent
          side="left"
          showCloseButton={false}
          className="cad-glass-surface gap-0 p-0 text-sidebar-foreground"
          style={{
            width: MOBILE_FILE_VIEWER_WIDTH,
            maxWidth: DESKTOP_FILE_VIEWER_MAX_WIDTH
          }}
        >
          <SheetHeaderPrimitive className="sr-only">
            <SheetTitle>CAD Viewer</SheetTitle>
            <SheetDescription>Browse files in the CAD catalog.</SheetDescription>
          </SheetHeaderPrimitive>
          <div className="flex h-full min-h-0 w-full flex-col" aria-label="CAD Viewer">
            {content}
          </div>
        </SheetContent>
      </Sheet>
    );
  }

  if (state !== "expanded") {
    return null;
  }

  const desktopWidth = `min(var(--sidebar-width), ${DESKTOP_FILE_VIEWER_MAX_WIDTH})`;
  const sidebarStyle = isMobile
    ? {
      width: MOBILE_FILE_VIEWER_WIDTH,
      maxWidth: DESKTOP_FILE_VIEWER_MAX_WIDTH
    }
    : {
      width: desktopWidth,
      flexBasis: desktopWidth,
      minWidth: `min(${DESKTOP_FILE_VIEWER_MIN_WIDTH}px, ${DESKTOP_FILE_VIEWER_MAX_WIDTH})`,
      maxWidth: DESKTOP_FILE_VIEWER_MAX_WIDTH
    };

  return (
    <aside
      className={cn(
        "cad-glass-surface pointer-events-auto z-30 flex h-full max-w-[calc(100vw_-_0.75rem)] flex-col border-r border-sidebar-border text-sidebar-foreground",
        isMobile
          ? "absolute inset-y-0 left-0 shadow-xl"
          : "relative shrink-0"
      )}
      style={sidebarStyle}
      aria-label="CAD Viewer"
    >
      {content}
    </aside>
  );
}
