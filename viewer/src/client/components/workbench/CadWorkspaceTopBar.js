import { Fragment, useEffect, useRef, useState } from "react";
import {
  Bot,
  Boxes,
  Check,
  ChevronDown,
  CircleCheck,
  Code,
  Copy,
  Cuboid,
  DraftingCompass,
  FileBox,
  Folder,
  Layers3,
  LoaderCircle,
  Moon,
  Package,
  Route,
  SlidersHorizontal,
  Sun
} from "lucide-react";
import {
  DEFAULT_VIEWER_SKILLS_INSTALL_COMMAND,
  isViewerReleaseMajorMinorNewer,
  isViewerReleaseNewer,
  viewerGithubLatestReleaseApiUrl,
  viewerGithubLatestReleaseUrl,
  normalizeViewerGithubUrl,
  viewerGithubReleaseUrl,
  viewerSkillsInstallCommandFromText
} from "../../../shared/viewerConfig.mjs";
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbList,
  BreadcrumbSeparator
} from "@/components/ui/breadcrumb";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSub,
  DropdownMenuSubContent,
  DropdownMenuSubTrigger,
  DropdownMenuTrigger
} from "@/components/ui/dropdown-menu";
import { ScrollArea } from "@/components/ui/scroll-area";
import { SidebarTrigger } from "@/components/ui/sidebar";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger
} from "@/components/ui/tooltip";
import { cn } from "@/ui/utils";
import { copyTextToClipboard } from "@/ui/clipboard";
import {
  themeSettingsSupportsSystemColorMode
} from "cadjs/lib/themeSettings";
import {
  DARK_COLOR_SCHEME_ID,
  LIGHT_COLOR_SCHEME_ID
} from "@/ui/colorScheme";
import {
  ENTRY_ICON_KIND,
  entryIconKind
} from "@/workbench/entryIconKind";
import { entryIconStatus } from "@/workbench/entryIconStatus";
import { ThemePresetDropdown } from "./ThemeSettingsPopover";
import FileAccessContextMenu from "./FileAccessContextMenu";
import {
  fileKey,
  listSidebarItems,
  sidebarDirectoryIdForEntry,
  sidebarDirectoryPath
} from "@/workbench/sidebar";
import viewerPackage from "../../../../package.json";

function collapsedBreadcrumbNodes(nodes) {
  if (nodes.length <= 4) {
    return nodes.map((node) => ({ type: "node", node }));
  }

  return [
    { type: "node", node: nodes[0] },
    { type: "ellipsis", label: "...", nodes: nodes.slice(1, -2) },
    ...nodes.slice(-2).map((node) => ({ type: "node", node }))
  ];
}

function fileSheetLabel(fileSheetKind) {
  if (fileSheetKind === "dxf") {
    return "DXF sheet";
  }
  if (fileSheetKind === "urdf") {
    return "URDF sheet";
  }
  if (fileSheetKind === "srdf") {
    return "SRDF sheet";
  }
  if (fileSheetKind === "sdf") {
    return "SDF sheet";
  }
  if (fileSheetKind === "step") {
    return "STEP sheet";
  }
  if (fileSheetKind === "implicit") {
    return "Implicit CAD sheet";
  }
  return "file sheet";
}

function sourceFormatForEntry(entry, entrySourceFormat) {
  const sourceFormat = typeof entrySourceFormat === "function"
    ? entrySourceFormat(entry)
    : (entry?.kind || "");
  return String(sourceFormat || "").trim().toLowerCase();
}

function entryStatusForMenu(entry, {
  entrySourceFormat,
  entryHasMesh,
  entryHasDxf,
  entryHasGcode,
  entryHasUrdf,
  activeGenerationFiles = [],
  activeStepArtifactGenerationFile = "",
  stepArtifactGenerationAvailable = true
}) {
  const sourceFormat = sourceFormatForEntry(entry, entrySourceFormat);
  const hasDxf = typeof entryHasDxf === "function" ? entryHasDxf(entry) : true;
  const hasGcode = typeof entryHasGcode === "function" ? entryHasGcode(entry) : true;
  const hasUrdf = typeof entryHasUrdf === "function" ? entryHasUrdf(entry) : true;
  const hasMesh = typeof entryHasMesh === "function" ? entryHasMesh(entry) : true;

  return entryIconStatus(entry, {
    sourceFormat,
    entryKey: fileKey(entry),
    hasMesh,
    hasDxf,
    hasGcode,
    hasUrdf,
    activeGenerationFiles,
    activeStepArtifactGenerationFile,
    stepArtifactGenerationAvailable
  });
}

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

function directoryTitle(directory) {
  return String(directory?.id || directory?.name || "Directory");
}

function buildBreadcrumbNodes({
  directoryTree,
  selectedEntry,
  selectedFileLabel,
  selectedFileTitle
}) {
  if (!directoryTree) {
    if (selectedEntry) {
      return [{
        type: "entry",
        label: selectedFileLabel,
        title: selectedFileTitle,
        entry: selectedEntry,
        menuDirectory: null
      }];
    }
    return [{
      type: "placeholder",
      label: selectedFileLabel,
      title: selectedFileTitle,
      menuDirectory: null
    }];
  }

  if (!selectedEntry) {
    return [{
      type: "placeholder",
      label: selectedFileLabel,
      title: selectedFileTitle,
      menuDirectory: directoryTree
    }];
  }

  const directoryId = sidebarDirectoryIdForEntry(selectedEntry);
  const directoryPath = sidebarDirectoryPath(directoryTree, directoryId);
  const directoryNodes = directoryPath.filter((directory) => String(directory.id || "").trim()).map((directory) => ({
    type: "directory",
    id: String(directory.id || ""),
    label: String(directory.name || "Folder"),
    title: directoryTitle(directory),
    directory,
    menuDirectory: directory
  }));

  return [
    ...directoryNodes,
    {
      type: "entry",
      label: selectedFileLabel,
      title: selectedFileTitle,
      entry: selectedEntry,
      menuDirectory: null
    }
  ];
}

function BreadcrumbEntryMenuItem({
  entry,
  selectedKey,
  onSelectEntry,
  sidebarLabelForEntry,
  entrySourceFormat,
  entryHasMesh,
  entryHasDxf,
  entryHasGcode,
  entryHasUrdf,
  activeGenerationFiles = [],
  activeStepArtifactGenerationFile = "",
  stepArtifactGenerationAvailable = true
}) {
  const key = fileKey(entry);
  const active = key === selectedKey;
  const label = typeof sidebarLabelForEntry === "function"
    ? sidebarLabelForEntry(entry)
    : key;
  const status = entryStatusForMenu(entry, {
    entrySourceFormat,
    entryHasMesh,
    entryHasDxf,
    entryHasGcode,
    entryHasUrdf,
    activeGenerationFiles,
    activeStepArtifactGenerationFile,
    stepArtifactGenerationAvailable
  });
  const { sourceFormat } = status;
  const EntryIcon = iconForEntry(entry, sourceFormat, status);
  const title = [
    label,
    status.statusLabel,
    entry?.kind,
    String(entry?.file || key)
  ].filter(Boolean).join(" | ");

  return (
    <DropdownMenuItem
      data-active={active}
      className={cn(
        "min-w-0 max-w-80 text-xs focus:bg-sidebar-accent focus:text-sidebar-accent-foreground",
        "data-[active=true]:bg-sidebar-accent data-[active=true]:font-medium data-[active=true]:text-sidebar-accent-foreground"
      )}
      title={title}
      disabled={!key || typeof onSelectEntry !== "function"}
      aria-current={active ? "page" : undefined}
      onSelect={() => {
        if (key && typeof onSelectEntry === "function") {
          onSelectEntry(key);
        }
      }}
    >
      <EntryIcon
        className={cn(
          "size-3.5 shrink-0",
          status.loading && "animate-spin"
        )}
        aria-hidden="true"
      />
      <span className="block min-w-0 flex-1 truncate">{label}</span>
    </DropdownMenuItem>
  );
}

function BreadcrumbDirectoryMenuItems({
  directory,
  selectedKey,
  onSelectEntry,
  sidebarLabelForEntry,
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
  onCopyFileAssetReference
}) {
  const items = listSidebarItems(directory);

  if (!items.length) {
    return (
      <DropdownMenuItem disabled className="max-w-80 text-xs">
        <Folder className="size-3.5 shrink-0" aria-hidden="true" />
        <span className="block min-w-0 truncate">{String(directory?.name || "Empty")}</span>
      </DropdownMenuItem>
    );
  }

  return items.map((item) => {
    if (item.type === "directory") {
      return (
        <BreadcrumbDirectorySubMenu
          key={item.key}
          directory={item.value}
          selectedKey={selectedKey}
          onSelectEntry={onSelectEntry}
          sidebarLabelForEntry={sidebarLabelForEntry}
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
          onCopyFileAssetReference={onCopyFileAssetReference}
        />
      );
    }

    return (
      <BreadcrumbEntryMenuItem
        key={item.key}
        entry={item.value}
        selectedKey={selectedKey}
        onSelectEntry={onSelectEntry}
        sidebarLabelForEntry={sidebarLabelForEntry}
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
        onCopyFileAssetReference={onCopyFileAssetReference}
      />
    );
  });
}

function DropdownMenuScrollArea({ children }) {
  return (
    <ScrollArea
      className="max-h-96 w-full"
      type="auto"
      viewportClassName="max-h-96"
    >
      {children}
    </ScrollArea>
  );
}

function BreadcrumbDirectorySubMenu({
  directory,
  selectedKey,
  onSelectEntry,
  sidebarLabelForEntry,
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
  onCopyFileAssetReference
}) {
  const title = directoryTitle(directory);

  return (
    <DropdownMenuSub>
      <DropdownMenuSubTrigger
        className="min-w-0 max-w-80 text-xs"
        title={title}
      >
        <Folder className="size-3.5 shrink-0" aria-hidden="true" />
        <span className="block min-w-0 flex-1 truncate">{String(directory?.name || "Folder")}</span>
      </DropdownMenuSubTrigger>
      <DropdownMenuSubContent className="w-max max-w-80">
        <DropdownMenuScrollArea>
          <BreadcrumbDirectoryMenuItems
            directory={directory}
            selectedKey={selectedKey}
            onSelectEntry={onSelectEntry}
            sidebarLabelForEntry={sidebarLabelForEntry}
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
            onCopyFileAssetReference={onCopyFileAssetReference}
          />
        </DropdownMenuScrollArea>
      </DropdownMenuSubContent>
    </DropdownMenuSub>
  );
}

function BreadcrumbNodeDropdown({
  node,
  current,
  selectedKey,
  onSelectEntry,
  sidebarLabelForEntry,
  entrySourceFormat,
  entryHasMesh,
  entryHasDxf,
  entryHasGcode,
  entryHasUrdf,
  activeGenerationFiles = [],
  activeStepArtifactGenerationFile = "",
  stepArtifactGenerationAvailable = true,
  selectedStepSourceStatus = null,
  canRevealFileAssets = false,
  canCopyFileAssetLinks = false,
  canCopyFileAssetPaths = false,
  fileAccessBusyKey = "",
  onDownloadFileAsset,
  onExportImplicitFile,
  onRevealFileAsset,
  onRevealInExplorerView,
  onCopyFileAssetReference,
  filenameLoadActivity
}) {
  const label = String(node?.label || "");
  const title = String(node?.title || label);
  const menuDirectory = node?.type === "directory" || node?.type === "placeholder"
    ? node?.menuDirectory || null
    : null;
  const canBrowse = !!menuDirectory && listSidebarItems(menuDirectory).length > 0;

  if (!canBrowse) {
    const labelNode = (
      <span
        className={cn(
          "inline-flex min-w-0 items-center gap-2 text-xs font-medium",
          current ? "max-w-[min(36rem,55vw)] text-foreground" : "max-w-32"
        )}
        title={title}
      >
        <span className="block min-w-0 truncate">{label}</span>
        {current && node?.type === "entry" ? (
          <FilenameLoadStatus activity={filenameLoadActivity} />
        ) : null}
      </span>
    );

    if (node?.type !== "entry" || !node?.entry) {
      return labelNode;
    }

    return (
      <FileAccessContextMenu
        entry={node.entry}
        stepSourceStatus={selectedStepSourceStatus}
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
        {labelNode}
      </FileAccessContextMenu>
    );
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          className={cn(
            "inline-flex min-w-0 items-center gap-2 rounded-sm text-xs font-medium transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
            current
              ? "max-w-[min(36rem,55vw)] text-foreground"
              : "max-w-32 text-muted-foreground"
          )}
          aria-label={`Browse ${label}`}
          aria-current={current ? "page" : undefined}
          title={title}
        >
          <span className="block min-w-0 truncate">{label}</span>
          {current && node?.type === "entry" ? (
            <FilenameLoadStatus activity={filenameLoadActivity} />
          ) : null}
          {node?.type === "placeholder" ? (
            <ChevronDown className="size-3.5 shrink-0 opacity-70" aria-hidden="true" />
          ) : null}
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" sideOffset={6} className="w-max max-w-80">
        <DropdownMenuScrollArea>
          <BreadcrumbDirectoryMenuItems
            directory={menuDirectory}
            selectedKey={selectedKey}
            onSelectEntry={onSelectEntry}
            sidebarLabelForEntry={sidebarLabelForEntry}
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
            onCopyFileAssetReference={onCopyFileAssetReference}
          />
        </DropdownMenuScrollArea>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function BreadcrumbEllipsisDropdown({
  nodes,
  selectedKey,
  onSelectEntry,
  sidebarLabelForEntry,
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
  onCopyFileAssetReference,
  title
}) {
  const hiddenNodes = Array.isArray(nodes) ? nodes.filter(Boolean) : [];
  const menuTitle = hiddenNodes.map((node) => node.label).join(" / ") || title;

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          className="inline-flex h-6 min-w-7 items-center justify-center rounded-md px-1.5 text-xs font-medium text-muted-foreground transition-colors hover:bg-sidebar-accent hover:text-sidebar-accent-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          aria-label="Show collapsed path folders"
          title={menuTitle}
        >
          <span aria-hidden="true">...</span>
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" sideOffset={6} className="w-max max-w-80">
        <DropdownMenuScrollArea>
          {hiddenNodes.map((node, index) => {
            if (node.type === "directory" && node.directory) {
              return (
                <BreadcrumbDirectorySubMenu
                  key={`${node.type}:${node.id}:${index}`}
                  directory={node.directory}
                  selectedKey={selectedKey}
                  onSelectEntry={onSelectEntry}
                  sidebarLabelForEntry={sidebarLabelForEntry}
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
                  onCopyFileAssetReference={onCopyFileAssetReference}
                />
              );
            }

            if (node.type === "entry" && node.entry) {
              return (
                <BreadcrumbEntryMenuItem
                  key={`${node.type}:${fileKey(node.entry)}:${index}`}
                  entry={node.entry}
                  selectedKey={selectedKey}
                  onSelectEntry={onSelectEntry}
                  sidebarLabelForEntry={sidebarLabelForEntry}
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
                  onCopyFileAssetReference={onCopyFileAssetReference}
                />
              );
            }

            return (
              <DropdownMenuItem key={`${node.type}:${node.label}:${index}`} disabled className="max-w-80 text-xs">
                <span className="block min-w-0 truncate">{node.label}</span>
              </DropdownMenuItem>
            );
          })}
        </DropdownMenuScrollArea>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function FilenameLoadStatus({ activity }) {
  const label = String(activity?.label || "").trim();
  if (!activity?.loading || !label) {
    return null;
  }

  const title = String(activity?.title || label).trim();

  return (
    <span
      role="status"
      aria-live="polite"
      title={title}
      className="inline-flex min-w-0 max-w-36 shrink items-center gap-1 rounded-md border border-border/70 bg-sidebar-accent px-1.5 py-0.5 text-[10px] font-medium leading-none text-sidebar-accent-foreground"
    >
      <LoaderCircle className="size-3 shrink-0 animate-spin" aria-hidden="true" />
      <span className="min-w-0 truncate">{label}</span>
    </span>
  );
}

function GitHubMark(props) {
  return (
    <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true" {...props}>
      <path d="M12 .5C5.65.5.5 5.65.5 12c0 5.09 3.29 9.4 7.86 10.92.58.1.79-.25.79-.56v-2.02c-3.2.7-3.87-1.37-3.87-1.37-.53-1.34-1.29-1.7-1.29-1.7-1.06-.73.08-.71.08-.71 1.17.08 1.79 1.2 1.79 1.2 1.04 1.78 2.73 1.27 3.4.97.1-.75.41-1.27.74-1.56-2.55-.29-5.24-1.28-5.24-5.68 0-1.25.45-2.28 1.2-3.08-.12-.29-.52-1.46.11-3.04 0 0 .98-.31 3.2 1.18A11.13 11.13 0 0 1 12 6.16c.99 0 1.98.13 2.91.39 2.22-1.49 3.2-1.18 3.2-1.18.63 1.58.23 2.75.11 3.04.75.8 1.2 1.83 1.2 3.08 0 4.41-2.69 5.39-5.25 5.67.42.36.79 1.08.79 2.17v3.03c0 .31.21.67.8.56A11.52 11.52 0 0 0 23.5 12C23.5 5.65 18.35.5 12 .5Z" />
    </svg>
  );
}

const topBarIconButtonClasses = "size-7";
const topBarIconClasses = "size-4";
const latestReleaseCacheKeyPrefix = "cad-viewer:latest-release:v1:";
const latestReleaseCacheTtlMs = 6 * 60 * 60 * 1000;
const updateVersionTooltipDelayMs = 250;
const passiveVersionTooltipDelayMs = 700;
const emptyLatestReleaseCheck = Object.freeze({
  updateAvailable: false,
  latestVersion: "",
  releaseUrl: "",
  installCommand: DEFAULT_VIEWER_SKILLS_INSTALL_COMMAND,
  latestReleaseNewer: false
});

function nextColorMode(currentColorMode) {
  return currentColorMode === DARK_COLOR_SCHEME_ID
    ? LIGHT_COLOR_SCHEME_ID
    : DARK_COLOR_SCHEME_ID;
}

function latestReleaseCacheKey(apiUrl) {
  return `${latestReleaseCacheKeyPrefix}${apiUrl}`;
}

function readLatestReleaseCache(apiUrl, now = Date.now()) {
  if (!apiUrl || typeof window === "undefined" || !window.localStorage) {
    return null;
  }

  try {
    const rawValue = window.localStorage.getItem(latestReleaseCacheKey(apiUrl));
    const value = rawValue ? JSON.parse(rawValue) : null;
    const expiresAt = Number(value?.expiresAt || 0);
    const latestVersion = String(value?.latestVersion || "").trim();
    const releaseUrl = String(value?.releaseUrl || "").trim();
    const installCommand = String(value?.installCommand || "").trim();
    if (!latestVersion || expiresAt <= now) {
      return null;
    }
    return { latestVersion, releaseUrl, installCommand };
  } catch {
    return null;
  }
}

function writeLatestReleaseCache(apiUrl, release, now = Date.now()) {
  if (!apiUrl || typeof window === "undefined" || !window.localStorage) {
    return;
  }

  const latestVersion = String(release?.latestVersion || "").trim();
  if (!latestVersion) {
    return;
  }

  try {
    window.localStorage.setItem(latestReleaseCacheKey(apiUrl), JSON.stringify({
      latestVersion,
      releaseUrl: String(release?.releaseUrl || "").trim(),
      installCommand: String(release?.installCommand || "").trim(),
      expiresAt: now + latestReleaseCacheTtlMs
    }));
  } catch {
    // Local storage availability is browser-policy dependent; the release check is optional.
  }
}

function latestReleaseFromPayload(payload, fallbackReleaseUrl = "") {
  const latestVersion = String(payload?.tag_name || "").trim();
  if (!latestVersion) {
    return null;
  }
  return {
    latestVersion,
    releaseUrl: String(payload?.html_url || fallbackReleaseUrl || "").trim(),
    installCommand: viewerSkillsInstallCommandFromText(
      payload?.body,
      DEFAULT_VIEWER_SKILLS_INSTALL_COMMAND
    )
  };
}

function latestReleaseCheckState(currentVersion, release) {
  const latestVersion = String(release?.latestVersion || "").trim();
  const releaseUrl = String(release?.releaseUrl || "").trim();
  const installCommand = String(release?.installCommand || DEFAULT_VIEWER_SKILLS_INSTALL_COMMAND).trim();
  if (!latestVersion) {
    return emptyLatestReleaseCheck;
  }
  const latestReleaseNewer = isViewerReleaseNewer(currentVersion, latestVersion);

  return {
    updateAvailable: isViewerReleaseMajorMinorNewer(currentVersion, latestVersion),
    latestVersion,
    releaseUrl,
    installCommand,
    latestReleaseNewer
  };
}

function useViewerLatestReleaseCheck({
  currentVersion,
  latestReleaseApiUrl,
  latestReleaseUrl,
  mockLatestVersion = "",
  mockLatestReleaseUrl = ""
}) {
  const [releaseCheck, setReleaseCheck] = useState(emptyLatestReleaseCheck);

  useEffect(() => {
    const version = String(currentVersion || "").trim();
    const apiUrl = String(latestReleaseApiUrl || "").trim();
    const mockedVersion = String(mockLatestVersion || "").trim();
    if (!version) {
      setReleaseCheck(emptyLatestReleaseCheck);
      return undefined;
    }

    if (mockedVersion) {
      setReleaseCheck(latestReleaseCheckState(version, {
        latestVersion: mockedVersion,
        releaseUrl: String(mockLatestReleaseUrl || latestReleaseUrl || "").trim(),
        installCommand: DEFAULT_VIEWER_SKILLS_INSTALL_COMMAND
      }));
      return undefined;
    }

    if (!apiUrl || typeof fetch !== "function") {
      setReleaseCheck(emptyLatestReleaseCheck);
      return undefined;
    }

    const cachedRelease = readLatestReleaseCache(apiUrl);
    if (cachedRelease) {
      setReleaseCheck(latestReleaseCheckState(version, cachedRelease));
      return undefined;
    }

    setReleaseCheck(emptyLatestReleaseCheck);
    const controller = new AbortController();
    fetch(apiUrl, {
      signal: controller.signal,
      headers: {
        Accept: "application/vnd.github+json"
      }
    })
      .then((response) => {
        if (!response.ok) {
          throw new Error(`GitHub latest release check failed with ${response.status}`);
        }
        return response.json();
      })
      .then((payload) => {
        if (controller.signal.aborted) {
          return;
        }
        const release = latestReleaseFromPayload(payload, latestReleaseUrl);
        if (!release) {
          if (!cachedRelease) {
            setReleaseCheck(emptyLatestReleaseCheck);
          }
          return;
        }
        writeLatestReleaseCache(apiUrl, release);
        setReleaseCheck(latestReleaseCheckState(version, release));
      })
      .catch((error) => {
        if (error?.name === "AbortError") {
          return;
        }
        if (!cachedRelease) {
          setReleaseCheck(emptyLatestReleaseCheck);
        }
      });

    return () => {
      controller.abort();
    };
  }, [currentVersion, latestReleaseApiUrl, latestReleaseUrl, mockLatestReleaseUrl, mockLatestVersion]);

  return releaseCheck;
}

function VersionTooltipRow({ label, version, action = null }) {
  const normalizedVersion = String(version || "").trim();
  if (!normalizedVersion) {
    return null;
  }

  return (
    <div className="flex min-w-0 flex-col items-start gap-1.5 px-0.5 text-left">
      <span className="text-[11px] font-medium leading-none text-muted-foreground">{label}</span>
      <div className="flex min-w-0 items-center gap-2">
        <span className="min-w-0 text-left font-mono text-[12px] leading-5 text-foreground tabular-nums">
          {normalizedVersion}
        </span>
        {action}
      </div>
    </div>
  );
}

function VersionReleaseLink({ version, releaseUrl, releaseCheck = emptyLatestReleaseCheck }) {
  const normalizedVersion = String(version || "").trim();
  const [installCopyStatus, setInstallCopyStatus] = useState("");
  const copyGestureHandledRef = useRef(false);

  if (!normalizedVersion) {
    return null;
  }

  const updateAvailable = Boolean(releaseCheck?.updateAvailable);
  const targetReleaseUrl = updateAvailable
    ? String(releaseCheck?.releaseUrl || releaseUrl || "").trim()
    : String(releaseUrl || "").trim();
  const latestVersion = String(releaseCheck?.latestVersion || "").trim();
  const latestReleaseNewer = Boolean(releaseCheck?.latestReleaseNewer);
  const latestVersionVisible = latestVersion && latestReleaseNewer;
  const latestReleaseUrl = latestVersionVisible
    ? String(releaseCheck?.releaseUrl || "").trim()
    : "";
  const installCommand = String(
    releaseCheck?.installCommand || DEFAULT_VIEWER_SKILLS_INSTALL_COMMAND
  ).trim() || DEFAULT_VIEWER_SKILLS_INSTALL_COMMAND;
  const upToDate = Boolean(latestVersion) && !latestReleaseNewer;
  const label = updateAvailable
    ? "Update CAD Viewer"
    : (targetReleaseUrl ? `Open release ${normalizedVersion}` : `Version ${normalizedVersion}`);

  const handleCopyInstallCommand = async (event) => {
    event.preventDefault();
    event.stopPropagation();
    if (copyGestureHandledRef.current) {
      return;
    }
    copyGestureHandledRef.current = true;
    globalThis.setTimeout(() => {
      copyGestureHandledRef.current = false;
    }, 250);
    try {
      await copyTextToClipboard(installCommand);
      setInstallCopyStatus("copied");
      globalThis.setTimeout(() => {
        setInstallCopyStatus("");
      }, 1600);
    } catch {
      setInstallCopyStatus("failed");
    }
  };

  const releaseButton = (
    <Button
      asChild={Boolean(targetReleaseUrl)}
      variant={updateAvailable ? "default" : "ghost"}
      size="xs"
      className={cn(
        "inline-flex rounded-sm px-2 text-xs font-medium leading-none",
        updateAvailable
          ? "h-6 px-2 text-[11px]"
          : "h-7 text-muted-foreground tabular-nums hover:text-sidebar-foreground"
      )}
      aria-label={label}
    >
      {targetReleaseUrl ? (
        <a href={targetReleaseUrl} target="_blank" rel="noreferrer">
          <span className="inline-flex items-center gap-1">
            {updateAvailable ? (
              <span>Update</span>
            ) : (
              <span>{normalizedVersion}</span>
            )}
          </span>
        </a>
      ) : (
        <span className="inline-flex items-center gap-1">
          {updateAvailable ? (
            <span>Update</span>
          ) : (
            <span>{normalizedVersion}</span>
          )}
        </span>
      )}
    </Button>
  );

  return (
    <Tooltip delayDuration={updateAvailable ? updateVersionTooltipDelayMs : passiveVersionTooltipDelayMs}>
      <TooltipTrigger asChild>
        {releaseButton}
      </TooltipTrigger>
      <TooltipContent
        side="bottom"
        sideOffset={6}
        className="cad-glass-popover w-fit max-w-[calc(100vw-1rem)] border border-border bg-popover p-2 text-left text-popover-foreground shadow-lg shadow-black/10"
        arrowClassName="bg-popover fill-popover"
      >
        <div className="inline-flex max-w-full flex-col gap-3">
          {latestVersionVisible ? (
            <div className="grid w-full min-w-0 grid-cols-2 gap-3">
              <VersionTooltipRow
                label="Current Version"
                version={normalizedVersion}
              />
              <VersionTooltipRow
                label="Latest Version"
                version={latestVersion}
                action={latestReleaseUrl ? (
                  <Button
                    asChild
                    variant="default"
                    size="xs"
                    className="h-4 !min-h-0 rounded-sm !px-1.5 !py-0 text-[10px] font-medium leading-none"
                    aria-label={`Update CAD Viewer to ${latestVersion}`}
                  >
                    <a href={latestReleaseUrl} target="_blank" rel="noreferrer">
                      Update
                    </a>
                  </Button>
                ) : null}
              />
            </div>
          ) : (
            <VersionTooltipRow
              label="Current Version"
              version={normalizedVersion}
            />
          )}
          <div className="flex min-w-0 flex-col gap-1.5">
            <div className="px-0.5 text-[11px] font-medium leading-none text-muted-foreground">Update Command</div>
            <div className="flex h-8 min-w-0 items-center gap-2 rounded-sm border border-border/60 bg-muted/35 p-1 pl-2">
              <code className="min-w-0 flex-1 whitespace-nowrap font-mono text-[11px] leading-5 text-foreground">
                {installCommand}
              </code>
              <Button
                type="button"
                variant="ghost"
                size="icon"
                className="inline-flex size-6 shrink-0 items-center justify-center rounded-sm border border-border text-foreground transition-colors hover:bg-accent hover:text-accent-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50"
                aria-label={installCopyStatus === "copied" ? "Install command copied" : "Copy install command"}
                onPointerDown={handleCopyInstallCommand}
                onClick={handleCopyInstallCommand}
              >
                {installCopyStatus === "copied" ? (
                  <Check className="size-3" aria-hidden="true" />
                ) : (
                  <Copy className="size-3" aria-hidden="true" />
                )}
              </Button>
            </div>
          </div>
          {installCopyStatus === "failed" ? (
            <div className="text-[11px] text-muted-foreground">Copy failed</div>
          ) : null}
          {upToDate ? (
            <div className="flex items-center gap-1.5 px-0.5 text-[11px] font-medium text-muted-foreground">
              <CircleCheck className="size-3 text-primary" aria-hidden="true" />
              <span>You are up to date</span>
            </div>
          ) : null}
        </div>
      </TooltipContent>
    </Tooltip>
  );
}

export default function CadWorkspaceTopBar({
  previewMode,
  sidebarLabelForEntry,
  directoryTree = null,
  selectedKey = "",
  selectedEntry,
  onSelectEntry,
  entrySourceFormat,
  entryHasMesh,
  entryHasDxf,
  entryHasGcode,
  entryHasUrdf,
  activeGenerationFiles = [],
  activeStepArtifactGenerationFile = "",
  stepArtifactGenerationAvailable = true,
  themePresets = [],
  themeSettings,
  themePresetId = "",
  resolvedColorSchemeMode = LIGHT_COLOR_SCHEME_ID,
  onColorSchemePreferenceChange,
  updateThemeSettings,
  handleResetThemeSettings,
  handleSaveCustomThemePreset,
  handleUpdateThemePresetSettings,
  handleDeleteCustomThemePreset,
  handleEditThemePreset,
  handleResetThemePresetToDefault,
  handleRestoreDefaultThemePresets,
  filenameLoadActivity = null,
  selectedStepSourceStatus = null,
  canRevealFileAssets = false,
  canCopyFileAssetLinks = false,
  canCopyFileAssetPaths = false,
  fileAccessBusyKey = "",
  onDownloadFileAsset,
  onExportImplicitFile,
  onRevealFileAsset,
  onRevealInExplorerView,
  onCopyFileAssetReference,
  fileSheetKind = "",
  fileSheetOpen = false,
  onToggleFileSheet,
  navigationAvailable = true
}) {
  const viewerVersion = String(viewerPackage.version || "").trim();
  const githubUrl = normalizeViewerGithubUrl(import.meta.env?.VIEWER_GITHUB_URL);
  const releaseUrl = viewerGithubReleaseUrl(viewerVersion, githubUrl);
  const latestReleaseUrl = viewerGithubLatestReleaseUrl(githubUrl);
  const latestReleaseApiUrl = previewMode ? "" : viewerGithubLatestReleaseApiUrl(githubUrl);
  const mockLatestVersion = import.meta.env.DEV
    ? String(import.meta.env?.VIEWER_MOCK_LATEST_VERSION || "").trim()
    : "";
  const mockLatestReleaseUrl = mockLatestVersion
    ? viewerGithubReleaseUrl(mockLatestVersion, githubUrl)
    : "";
  const releaseCheck = useViewerLatestReleaseCheck({
    currentVersion: viewerVersion,
    latestReleaseApiUrl,
    latestReleaseUrl,
    mockLatestVersion,
    mockLatestReleaseUrl
  });

  if (previewMode) {
    return null;
  }

  const selectedFileLabel = selectedEntry && typeof sidebarLabelForEntry === "function"
    ? sidebarLabelForEntry(selectedEntry)
    : "Select a file";
  const selectedFileTitle = selectedEntry
    ? String(selectedEntry.file || selectedEntry.id || selectedFileLabel)
    : selectedFileLabel;
  const breadcrumbAvailable = navigationAvailable || Boolean(selectedEntry);
  const breadcrumbNodes = buildBreadcrumbNodes({
    directoryTree: navigationAvailable ? directoryTree : null,
    selectedEntry,
    selectedFileLabel,
    selectedFileTitle
  });
  const breadcrumbItems = collapsedBreadcrumbNodes(breadcrumbNodes);
  const mobileBreadcrumbNode = breadcrumbNodes[breadcrumbNodes.length - 1] || null;
  const activeIconButtonClasses = "bg-accent text-accent-foreground";
  const showFileSheetToggle = !!fileSheetKind && typeof onToggleFileSheet === "function";
  const fileSheetToggleLabel = fileSheetOpen
    ? `Collapse ${fileSheetLabel(fileSheetKind)}`
    : `Expand ${fileSheetLabel(fileSheetKind)}`;
  const showThemeColorModeToggle = themeSettingsSupportsSystemColorMode(themeSettings);
  const activeColorSchemeMode = resolvedColorSchemeMode === DARK_COLOR_SCHEME_ID
    ? DARK_COLOR_SCHEME_ID
    : LIGHT_COLOR_SCHEME_ID;
  const nextColorSchemeMode = nextColorMode(activeColorSchemeMode);
  const activeColorSchemeModeLabel = activeColorSchemeMode === DARK_COLOR_SCHEME_ID ? "dark" : "light";
  const nextColorSchemeModeLabel = nextColorSchemeMode === DARK_COLOR_SCHEME_ID ? "dark" : "light";
  const colorModeToggleLabel = `Browser color mode: ${activeColorSchemeModeLabel}. Switch to ${nextColorSchemeModeLabel} mode.`;
  const ColorModeIcon = activeColorSchemeMode === DARK_COLOR_SCHEME_ID ? Moon : Sun;

  const handleThemeColorModeToggle = () => {
    if (typeof onColorSchemePreferenceChange !== "function") {
      return;
    }
    onColorSchemePreferenceChange(nextColorSchemeMode);
  };

  return (
    <header
      className="cad-glass-surface pointer-events-auto flex h-11 shrink-0 items-center gap-2 border-b border-sidebar-border px-2 text-sidebar-foreground"
    >
      {navigationAvailable ? (
        <SidebarTrigger
          title="Toggle CAD Viewer"
          aria-label="Toggle CAD Viewer"
          className="shrink-0"
        />
      ) : null}

      {breadcrumbAvailable ? (
      <Breadcrumb className="min-w-0 flex-1 overflow-hidden">
        <ScrollArea
          className="h-8 min-w-0 whitespace-nowrap"
          type="auto"
          viewportClassName="overflow-y-hidden"
          scrollbars="horizontal"
        >
          {mobileBreadcrumbNode ? (
            <BreadcrumbList className="flex h-8 min-w-full flex-nowrap gap-1.5 pr-2 text-xs sm:hidden">
              <BreadcrumbItem className="min-w-0">
                <BreadcrumbNodeDropdown
                  node={mobileBreadcrumbNode}
                  current
                  selectedKey={selectedKey}
                  onSelectEntry={onSelectEntry}
                  sidebarLabelForEntry={sidebarLabelForEntry}
                  entrySourceFormat={entrySourceFormat}
                  entryHasMesh={entryHasMesh}
                  entryHasDxf={entryHasDxf}
                  entryHasGcode={entryHasGcode}
                  entryHasUrdf={entryHasUrdf}
                  activeGenerationFiles={activeGenerationFiles}
                  activeStepArtifactGenerationFile={activeStepArtifactGenerationFile}
                  stepArtifactGenerationAvailable={stepArtifactGenerationAvailable}
                  selectedStepSourceStatus={selectedStepSourceStatus}
                  canRevealFileAssets={canRevealFileAssets}
                  canCopyFileAssetLinks={canCopyFileAssetLinks}
                  canCopyFileAssetPaths={canCopyFileAssetPaths}
                  fileAccessBusyKey={fileAccessBusyKey}
                  onDownloadFileAsset={onDownloadFileAsset}
                  onExportImplicitFile={onExportImplicitFile}
                  onRevealFileAsset={onRevealFileAsset}
                  onRevealInExplorerView={onRevealInExplorerView}
                  onCopyFileAssetReference={onCopyFileAssetReference}
                  filenameLoadActivity={filenameLoadActivity}
                />
              </BreadcrumbItem>
            </BreadcrumbList>
          ) : null}
          <BreadcrumbList className="hidden h-8 min-w-full w-max flex-nowrap gap-1.5 pr-2 text-xs sm:flex sm:gap-1.5">
            {breadcrumbItems.map((item, index) => (
              <Fragment key={`${item.type}:${item.node?.type || ""}:${item.node?.id || item.node?.label || index}:${index}`}>
                <BreadcrumbItem className="min-w-0">
                  {item.type === "ellipsis" ? (
                    <BreadcrumbEllipsisDropdown
                      nodes={item.nodes}
                      selectedKey={selectedKey}
                      onSelectEntry={onSelectEntry}
                      sidebarLabelForEntry={sidebarLabelForEntry}
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
                      onCopyFileAssetReference={onCopyFileAssetReference}
                      title={selectedFileTitle}
                    />
                  ) : (
                    <BreadcrumbNodeDropdown
                      node={item.node}
                      current={index === breadcrumbItems.length - 1}
                      selectedKey={selectedKey}
                      onSelectEntry={onSelectEntry}
                      sidebarLabelForEntry={sidebarLabelForEntry}
                      entrySourceFormat={entrySourceFormat}
                      entryHasMesh={entryHasMesh}
                      entryHasDxf={entryHasDxf}
                      entryHasGcode={entryHasGcode}
                      entryHasUrdf={entryHasUrdf}
                      activeGenerationFiles={activeGenerationFiles}
                      activeStepArtifactGenerationFile={activeStepArtifactGenerationFile}
                      stepArtifactGenerationAvailable={stepArtifactGenerationAvailable}
                      selectedStepSourceStatus={selectedStepSourceStatus}
                      canRevealFileAssets={canRevealFileAssets}
                      canCopyFileAssetLinks={canCopyFileAssetLinks}
                      canCopyFileAssetPaths={canCopyFileAssetPaths}
                      fileAccessBusyKey={fileAccessBusyKey}
                      onDownloadFileAsset={onDownloadFileAsset}
                      onExportImplicitFile={onExportImplicitFile}
                      onRevealFileAsset={onRevealFileAsset}
                      onRevealInExplorerView={onRevealInExplorerView}
                      onCopyFileAssetReference={onCopyFileAssetReference}
                      filenameLoadActivity={filenameLoadActivity}
                    />
                  )}
                </BreadcrumbItem>
                {index < breadcrumbItems.length - 1 ? (
                  <BreadcrumbSeparator className="text-muted-foreground/60" />
                ) : null}
              </Fragment>
            ))}
          </BreadcrumbList>
        </ScrollArea>
      </Breadcrumb>
      ) : (
        <div className="min-w-0 flex-1" />
      )}

      <TooltipProvider delayDuration={250}>
        <div className="flex shrink-0 items-center gap-1.5">
          <VersionReleaseLink
            version={viewerVersion}
            releaseUrl={releaseUrl}
            releaseCheck={releaseCheck}
          />
          {githubUrl ? (
            <Button
              asChild
              variant="ghost"
              size="icon-sm"
              aria-label="Open GitHub repository"
              title="Open GitHub repository"
              className={topBarIconButtonClasses}
            >
              <a href={githubUrl} target="_blank" rel="noreferrer">
                <GitHubMark className={topBarIconClasses} />
              </a>
            </Button>
          ) : null}

          <ThemePresetDropdown
            themePresets={themePresets}
            themeSettings={themeSettings}
            themePresetId={themePresetId}
            updateThemeSettings={updateThemeSettings}
            handleResetThemeSettings={handleResetThemeSettings}
            handleSaveCustomThemePreset={handleSaveCustomThemePreset}
            handleUpdateThemePresetSettings={handleUpdateThemePresetSettings}
            handleDeleteCustomThemePreset={handleDeleteCustomThemePreset}
            handleEditThemePreset={handleEditThemePreset}
            handleResetThemePresetToDefault={handleResetThemePresetToDefault}
            handleRestoreDefaultThemePresets={handleRestoreDefaultThemePresets}
            triggerClassName={topBarIconButtonClasses}
            iconClassName={topBarIconClasses}
          />

          {showThemeColorModeToggle ? (
            <Button
              type="button"
              variant="ghost"
              size="icon"
              aria-label={colorModeToggleLabel}
              title={colorModeToggleLabel}
              disabled={typeof onColorSchemePreferenceChange !== "function"}
              onClick={handleThemeColorModeToggle}
              className={topBarIconButtonClasses}
            >
              <ColorModeIcon className={topBarIconClasses} />
              <span className="sr-only">{colorModeToggleLabel}</span>
            </Button>
          ) : null}

          {showFileSheetToggle ? (
            <Button
              type="button"
              variant="ghost"
              size="icon"
              aria-label={fileSheetToggleLabel}
              title={fileSheetToggleLabel}
              aria-pressed={fileSheetOpen}
              onClick={onToggleFileSheet}
              className={`${topBarIconButtonClasses} ${fileSheetOpen ? activeIconButtonClasses : ""}`}
            >
              <SlidersHorizontal className={topBarIconClasses} />
              <span className="sr-only">{fileSheetToggleLabel}</span>
            </Button>
          ) : null}
        </div>
      </TooltipProvider>
    </header>
  );
}
