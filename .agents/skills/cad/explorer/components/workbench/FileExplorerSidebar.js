import {
  Bot,
  Boxes,
  ChevronRight,
  Download,
  DraftingCompass,
  LoaderCircle,
  Package,
  TriangleAlert
} from "lucide-react";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger
} from "@/components/ui/collapsible";
import { Button } from "@/components/ui/button";
import {
  ContextMenu,
  ContextMenuContent,
  ContextMenuItem,
  ContextMenuTrigger
} from "@/components/ui/context-menu";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Sidebar,
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
  SidebarTrigger,
  useSidebar
} from "@/components/ui/sidebar";
import { cn } from "@/lib/utils";
import { RENDER_FORMAT } from "../../lib/workbench/constants";
import {
  fileKey,
  listSidebarItems,
  sidebarLabelForEntry
} from "../../lib/workbench/sidebar";

function stepArtifactsMissing(entry, sourceFormat) {
  return (
    sourceFormat === RENDER_FORMAT.STEP &&
    entry?.stepArtifact?.ok === false &&
    String(entry?.stepArtifact?.error?.code || "") === "missing_glb"
  );
}

function iconForEntry(entry, sourceFormat, pending, missingArtifacts) {
  if (missingArtifacts) {
    return TriangleAlert;
  }
  if (pending) {
    return LoaderCircle;
  }
  if (entry?.kind === "assembly") {
    return Boxes;
  }
  if (sourceFormat === RENDER_FORMAT.DXF) {
    return DraftingCompass;
  }
  if (entry?.kind === "urdf") {
    return Bot;
  }
  return Package;
}

function FileEntryButton({
  entry,
  depth,
  selectedKey,
  onSelectEntry,
  entrySourceFormat,
  entryHasMesh,
  entryHasDxf,
  entryHasUrdf,
  nested = false
}) {
  const { isMobile, setOpenMobile } = useSidebar();
  const key = fileKey(entry);
  const active = key === selectedKey;
  const label = sidebarLabelForEntry(entry);
  const sourceFormat = entrySourceFormat(entry);
  const pending = sourceFormat === RENDER_FORMAT.DXF
    ? !entryHasDxf(entry)
    : sourceFormat === RENDER_FORMAT.URDF
      ? !entryHasUrdf(entry)
      : !entryHasMesh(entry);
  const missingArtifacts = stepArtifactsMissing(entry, sourceFormat);
  const EntryIcon = iconForEntry(entry, sourceFormat, pending, missingArtifacts);
  const title = [
    label,
    missingArtifacts ? "artifacts missing" : pending ? "pending" : "ready",
    entry?.kind,
    String(entry?.source?.path || entry?.step?.path || "")
  ].filter(Boolean).join(" | ");

  const handleDownload = () => {
    const sourcePath = entry?.source?.path || entry?.step?.path;
    if (!sourcePath) return;
    const url = `/${sourcePath}`;
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = sourcePath.split("/").pop() || sourcePath;
    document.body.appendChild(anchor);
    anchor.click();
    document.body.removeChild(anchor);
  };

  return (
    <ContextMenu>
      <ContextMenuTrigger asChild>
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
          <EntryIcon className={cn(pending && !missingArtifacts && "animate-spin")} aria-hidden="true" />
          <span className="block min-w-0 flex-1 max-w-full overflow-hidden text-ellipsis whitespace-nowrap">{label}</span>
        </SidebarMenuButton>
      </ContextMenuTrigger>
      <ContextMenuContent>
        <ContextMenuItem onSelect={handleDownload}>
          <Download className="size-4" aria-hidden="true" />
          Download
        </ContextMenuItem>
      </ContextMenuContent>
    </ContextMenu>
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
  entryHasUrdf,
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
                    entryHasUrdf={entryHasUrdf}
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
                    entryHasUrdf={entryHasUrdf}
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

  if (isMobile || state !== "expanded") {
    return null;
  }

  return (
    <Button
      type="button"
      variant="ghost"
      size="sm"
      aria-label="Resize file explorer sidebar"
      title="Resize sidebar"
      onPointerDown={onStartResize}
      className="group/sidebar-resize absolute inset-y-0 -right-1.5 z-30 hidden h-auto w-3 cursor-col-resize touch-none items-stretch justify-center rounded-none px-0 py-0 hover:bg-transparent md:flex"
    >
      <span className="my-2 w-px rounded-full bg-transparent transition-colors group-hover/sidebar-resize:bg-sidebar-border group-focus-visible/sidebar-resize:bg-ring" />
    </Button>
  );
}

export default function FileExplorerSidebar({
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
  entryHasUrdf,
  onStartResize
}) {
  if (previewMode) {
    return null;
  }

  const queryActive = query.trim().length > 0;
  const hasMatches = filteredEntries.length > 0;
  const hasEntries = catalogEntries.length > 0;

  return (
    <Sidebar collapsible="offcanvas">
      <SidebarHeader>
        <div className="flex h-7 items-center gap-2 px-2">
          <div className="min-w-0 flex-1 truncate text-xs font-semibold">
            CAD Explorer
          </div>
          <SidebarTrigger
            title="Toggle CAD Explorer"
            aria-label="Toggle CAD Explorer"
            className="shrink-0"
          />
        </div>
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
        <ScrollArea className="cad-file-explorer-scroll min-h-0 min-w-0 flex-1 overflow-x-hidden">
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
                          entryHasUrdf={entryHasUrdf}
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
                          entryHasUrdf={entryHasUrdf}
                        />
                      </SidebarMenuItem>
                    );
                  })}
                </SidebarMenu>
              ) : hasEntries ? (
                <p className="px-2 py-3 text-xs text-muted-foreground">No CAD entries match this filter.</p>
              ) : (
                <p className="px-2 py-3 text-xs text-muted-foreground">No CAD entries found.</p>
              )}
            </SidebarGroupContent>
          </SidebarGroup>
        </ScrollArea>
      </SidebarContent>
      <SidebarResizeHandle onStartResize={onStartResize} />
    </Sidebar>
  );
}
