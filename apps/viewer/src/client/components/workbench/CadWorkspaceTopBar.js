import { Fragment, useEffect, useRef, useState } from "react";
import {
  Check,
  CircleCheck,
  Contrast,
  Copy,
  Folder,
  LoaderCircle,
  SlidersHorizontal
} from "lucide-react";
import EntryIcon from "./EntryIcon";
import {
  DEFAULT_VIEWER_SKILLS_INSTALL_COMMAND,
  DEFAULT_VIEWER_SKILLS_UPDATE_PROMPT,
  isViewerReleaseNewer,
  isViewerReleaseUpdateSuggested,
  normalizeViewerReleaseVersion,
  viewerGithubLatestReleaseApiUrl,
  viewerGithubLatestReleaseUrl,
  normalizeViewerDiscordUrl,
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
import { entryIconStatus } from "@/workbench/entryIconStatus";
import FileAccessContextMenu from "./FileAccessContextMenu";
import {
  fileKey,
  listSidebarItems,
} from "@/workbench/sidebar";
import {
  buildBreadcrumbNodes,
  collapsedBreadcrumbNodes,
  directoryTitle,
  ellipsisBreadcrumbMenuDirectory
} from "@/workbench/breadcrumbs";
import viewerPackage from "../../../../package.json";

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
  entryHasUrdf,
  activeStepArtifactGenerationFile = "",
  stepArtifactGenerationAvailable = true
}) {
  const sourceFormat = sourceFormatForEntry(entry, entrySourceFormat);
  const hasDxf = typeof entryHasDxf === "function" ? entryHasDxf(entry) : true;
  const hasUrdf = typeof entryHasUrdf === "function" ? entryHasUrdf(entry) : true;
  const hasMesh = typeof entryHasMesh === "function" ? entryHasMesh(entry) : true;

  return entryIconStatus(entry, {
    sourceFormat,
    hasMesh,
    hasDxf,
    hasUrdf,
    activeStepArtifactGenerationFile,
    stepArtifactGenerationAvailable
  });
}

function BreadcrumbEntryMenuItem({
  entry,
  selectedKey,
  onSelectEntry,
  sidebarLabelForEntry,
  entrySourceFormat,
  entryHasMesh,
  entryHasDxf,
  entryHasUrdf,
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
    entryHasUrdf,
    activeStepArtifactGenerationFile,
    stepArtifactGenerationAvailable
  });
  const { sourceFormat } = status;
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
        "data-[active=true]:bg-sidebar-accent data-[active=true]:text-sidebar-accent-foreground"
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
        entry={entry}
        sourceFormat={sourceFormat}
        status={status}
        className="size-3.5 shrink-0"
        spinning={status.loading}
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
  entryHasUrdf,
  activeStepArtifactGenerationFile = "",
  stepArtifactGenerationAvailable = true,
  canCopyFileAssetPaths = false,
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
          entryHasUrdf={entryHasUrdf}
          activeStepArtifactGenerationFile={activeStepArtifactGenerationFile}
          stepArtifactGenerationAvailable={stepArtifactGenerationAvailable}
          canCopyFileAssetPaths={canCopyFileAssetPaths}
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
        entryHasUrdf={entryHasUrdf}
        activeStepArtifactGenerationFile={activeStepArtifactGenerationFile}
        stepArtifactGenerationAvailable={stepArtifactGenerationAvailable}
        canCopyFileAssetPaths={canCopyFileAssetPaths}
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
  label = "",
  title: titleProp = "",
  selectedKey,
  onSelectEntry,
  sidebarLabelForEntry,
  entrySourceFormat,
  entryHasMesh,
  entryHasDxf,
  entryHasUrdf,
  activeStepArtifactGenerationFile = "",
  stepArtifactGenerationAvailable = true,
  canCopyFileAssetPaths = false,
  onCopyFileAssetReference
}) {
  const labelText = String(label || directory?.name || "Folder");
  const title = String(titleProp || directoryTitle(directory));

  return (
    <DropdownMenuSub>
      <DropdownMenuSubTrigger
        className="min-w-0 max-w-80 text-xs"
        title={title}
      >
        <Folder className="size-3.5 shrink-0" aria-hidden="true" />
        <span className="block min-w-0 flex-1 truncate">{labelText}</span>
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
            entryHasUrdf={entryHasUrdf}
            activeStepArtifactGenerationFile={activeStepArtifactGenerationFile}
            stepArtifactGenerationAvailable={stepArtifactGenerationAvailable}
            canCopyFileAssetPaths={canCopyFileAssetPaths}
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
  entryHasUrdf,
  activeStepArtifactGenerationFile = "",
  stepArtifactGenerationAvailable = true,
  selectedStepSourceStatus = null,
  canCopyFileAssetPaths = false,
  onRevealInExplorerView,
  onCopyFileAssetReference,
  filenameLoadActivity
}) {
  const label = String(node?.label || "");
  const title = String(node?.title || label);
  const menuDirectory = node?.type === "directory" || node?.type === "placeholder" || node?.type === "entry"
    ? node?.menuDirectory || null
    : null;
  const canBrowse = !!menuDirectory && listSidebarItems(menuDirectory).length > 0;

  if (!canBrowse) {
    const labelNode = (
      <span
        className={cn(
          "inline-flex min-w-0 items-center gap-2 text-xs",
          current ? "max-w-[min(36rem,55vw)] text-foreground" : "max-w-32"
        )}
        title={title}
      >
        {current && node?.type === "entry" ? (
          <FilenameLoadStatus activity={filenameLoadActivity} />
        ) : null}
        <span className="block min-w-0 truncate">{label}</span>
      </span>
    );

    if (node?.type !== "entry" || !node?.entry) {
      return labelNode;
    }

    return (
      <FileAccessContextMenu
        entry={node.entry}
        stepSourceStatus={selectedStepSourceStatus}
        canCopyFileAssetPaths={canCopyFileAssetPaths}
        onRevealInExplorerView={onRevealInExplorerView}
        onCopyFileAssetReference={onCopyFileAssetReference}
      >
        {labelNode}
      </FileAccessContextMenu>
    );
  }

  const triggerButton = (
    <button
      type="button"
      className={cn(
        "inline-flex min-w-0 items-center gap-2 rounded-sm text-xs transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
        current
          ? "max-w-[min(36rem,55vw)] text-foreground"
          : "max-w-32 text-muted-foreground"
      )}
      aria-label={`Browse ${label}`}
      aria-current={current ? "page" : undefined}
      title={title}
      onPointerDown={(event) => {
        if (event.button === 1) {
          event.preventDefault();
        }
      }}
    >
      {current && node?.type === "entry" ? (
        <FilenameLoadStatus activity={filenameLoadActivity} />
      ) : null}
      <span className="block min-w-0 truncate">{label}</span>
    </button>
  );
  const dropdownTrigger = (
    <DropdownMenuTrigger asChild>
      {triggerButton}
    </DropdownMenuTrigger>
  );
  const trigger = node?.type === "entry" && node?.entry ? (
    <FileAccessContextMenu
      entry={node.entry}
      stepSourceStatus={selectedStepSourceStatus}
      canCopyFileAssetPaths={canCopyFileAssetPaths}
      onRevealInExplorerView={onRevealInExplorerView}
      onCopyFileAssetReference={onCopyFileAssetReference}
    >
      {dropdownTrigger}
    </FileAccessContextMenu>
  ) : dropdownTrigger;

  return (
    <DropdownMenu>
      {trigger}
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
            entryHasUrdf={entryHasUrdf}
            activeStepArtifactGenerationFile={activeStepArtifactGenerationFile}
            stepArtifactGenerationAvailable={stepArtifactGenerationAvailable}
            canCopyFileAssetPaths={canCopyFileAssetPaths}
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
  entryHasUrdf,
  activeStepArtifactGenerationFile = "",
  stepArtifactGenerationAvailable = true,
  canCopyFileAssetPaths = false,
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
          className="inline-flex h-6 min-w-7 items-center justify-center rounded-md px-1.5 text-xs text-muted-foreground transition-colors hover:bg-sidebar-accent hover:text-sidebar-accent-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          aria-label="Show collapsed path folders"
          title={menuTitle}
        >
          <span aria-hidden="true">...</span>
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" sideOffset={6} className="w-max max-w-80">
        <DropdownMenuScrollArea>
          {hiddenNodes.map((node, index) => {
            const directory = ellipsisBreadcrumbMenuDirectory(node);
            if (node.type === "directory" && directory) {
              return (
                <BreadcrumbDirectorySubMenu
                  key={`${node.type}:${node.id}:${index}`}
                  directory={directory}
                  label={node.label}
                  title={node.title}
                  selectedKey={selectedKey}
                  onSelectEntry={onSelectEntry}
                  sidebarLabelForEntry={sidebarLabelForEntry}
                  entrySourceFormat={entrySourceFormat}
                  entryHasMesh={entryHasMesh}
                  entryHasDxf={entryHasDxf}
                  entryHasUrdf={entryHasUrdf}
                  activeStepArtifactGenerationFile={activeStepArtifactGenerationFile}
                  stepArtifactGenerationAvailable={stepArtifactGenerationAvailable}
                  canCopyFileAssetPaths={canCopyFileAssetPaths}
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
                  entryHasUrdf={entryHasUrdf}
                  activeStepArtifactGenerationFile={activeStepArtifactGenerationFile}
                  stepArtifactGenerationAvailable={stepArtifactGenerationAvailable}
                  canCopyFileAssetPaths={canCopyFileAssetPaths}
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

/**
 * A bare spinner, left of the filename. No chip, no text, no percent.
 *
 * The overlay already carries the words and the number; repeating them in the breadcrumb
 * gave the same state two competing readouts that could disagree mid-poll. This says only
 * "this file is busy" and leaves the detail to the one place that owns it. The label still
 * rides on `title` and the screen-reader text, so nothing is lost for a11y or hover.
 */
function FilenameLoadStatus({ activity }) {
  if (!activity?.loading) {
    return null;
  }

  const label = String(activity?.label || "").trim();
  const title = String(activity?.title || label || "Loading").trim();

  return (
    <span role="status" aria-live="polite" title={title} className="inline-flex shrink-0 items-center">
      <LoaderCircle className="size-3 shrink-0 animate-spin text-muted-foreground" aria-hidden="true" />
      <span className="sr-only">{title}</span>
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

function DiscordMark(props) {
  return (
    <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true" {...props}>
      <path d="M20.32 4.37a19.8 19.8 0 0 0-4.89-1.51.07.07 0 0 0-.07.03c-.21.38-.44.86-.61 1.25a18.27 18.27 0 0 0-5.49 0 12.64 12.64 0 0 0-.62-1.25.08.08 0 0 0-.07-.03 19.74 19.74 0 0 0-4.89 1.51.07.07 0 0 0-.03.03C.53 9.05-.32 13.58.1 18.06a.08.08 0 0 0 .03.06 19.9 19.9 0 0 0 5.99 3.03.08.08 0 0 0 .08-.03c.46-.63.87-1.3 1.23-1.99a.08.08 0 0 0-.04-.11 13.1 13.1 0 0 1-1.87-.89.08.08 0 0 1-.01-.13c.13-.09.25-.19.37-.29a.07.07 0 0 1 .08-.01c3.93 1.79 8.18 1.79 12.06 0a.07.07 0 0 1 .08.01c.12.1.25.2.37.29a.08.08 0 0 1-.01.13 12.3 12.3 0 0 1-1.87.89.08.08 0 0 0-.04.11c.36.7.77 1.36 1.23 1.99a.08.08 0 0 0 .08.03 19.84 19.84 0 0 0 6-3.03.08.08 0 0 0 .03-.05c.5-5.18-.84-9.67-3.55-13.66a.06.06 0 0 0-.02-.04ZM8.02 15.33c-1.18 0-2.16-1.09-2.16-2.42s.96-2.42 2.16-2.42c1.21 0 2.18 1.1 2.16 2.42 0 1.33-.96 2.42-2.16 2.42Zm7.98 0c-1.18 0-2.16-1.09-2.16-2.42s.96-2.42 2.16-2.42c1.21 0 2.18 1.1 2.16 2.42 0 1.33-.95 2.42-2.16 2.42Z" />
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
  // `tag_name` is `v0.5.0`; the chip, the aria-label and the comparison all want `0.5.0`.
  // Normalized ONCE, here, so nothing downstream has to know about tag spellings.
  const latestVersion = normalizeViewerReleaseVersion(payload?.tag_name);
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
    updateAvailable: isViewerReleaseUpdateSuggested(currentVersion, latestVersion),
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
      <span className="text-tiny leading-none text-muted-foreground">{label}</span>
      <div className="flex min-w-0 items-center gap-2">
        <span className="min-w-0 text-left font-mono text-xs leading-5 text-foreground tabular-nums">
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
  const [promptCopyStatus, setPromptCopyStatus] = useState("");
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
  const updatePrompt = DEFAULT_VIEWER_SKILLS_UPDATE_PROMPT;
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

  const handleCopyUpdatePrompt = async (event) => {
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
      await copyTextToClipboard(updatePrompt);
      setPromptCopyStatus("copied");
      globalThis.setTimeout(() => {
        setPromptCopyStatus("");
      }, 1600);
    } catch {
      setPromptCopyStatus("failed");
    }
  };

  const releaseButton = (
    <Button
      asChild={Boolean(targetReleaseUrl)}
      variant={updateAvailable ? "default" : "ghost"}
      size="xs"
      className={cn(
        "inline-flex rounded-sm px-2 text-xs leading-none",
        updateAvailable
          ? "h-6 px-2 text-tiny"
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
                    className="h-4 !min-h-0 rounded-sm !px-1.5 !py-0 text-micro leading-none"
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
            <div className="px-0.5 text-tiny leading-none text-muted-foreground">In your terminal</div>
            <div className="flex h-8 min-w-0 items-center gap-2 rounded-sm border border-border/60 bg-muted/35 p-1 pl-2">
              <code className="min-w-0 flex-1 whitespace-nowrap font-mono text-tiny leading-5 text-foreground">
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
          <div className="flex min-w-0 flex-col gap-1.5">
            {/* The same update, handed to an agent instead of run in a terminal. */}
            <div className="px-0.5 text-tiny leading-none text-muted-foreground">
              Or ask your agent
            </div>
            {/* Shows the message VERBATIM, wrapped rather than truncated: the row above it is
                the literal command it copies, so a summarised label here reads as though the
                agent were being sent something vaguer than the terminal option. It is not --
                the same command is in it. The width cap is what makes it wrap. */}
            <div className="flex min-h-8 min-w-0 items-center gap-2 rounded-sm border border-border/60 bg-muted/35 p-1 pl-2">
              <span className="min-w-0 max-w-[15.5rem] flex-1 text-tiny leading-4 text-foreground">
                {updatePrompt}
              </span>
              <Button
                type="button"
                variant="ghost"
                size="icon"
                className="inline-flex size-6 shrink-0 items-center justify-center rounded-sm border border-border text-foreground transition-colors hover:bg-accent hover:text-accent-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50"
                aria-label={promptCopyStatus === "copied" ? "Agent message copied" : "Copy agent message"}
                title={updatePrompt}
                onPointerDown={handleCopyUpdatePrompt}
                onClick={handleCopyUpdatePrompt}
              >
                {promptCopyStatus === "copied" ? (
                  <Check className="size-3" aria-hidden="true" />
                ) : (
                  <Copy className="size-3" aria-hidden="true" />
                )}
              </Button>
            </div>
          </div>
          {installCopyStatus === "failed" || promptCopyStatus === "failed" ? (
            <div className="text-tiny text-muted-foreground">Copy failed</div>
          ) : null}
          {upToDate ? (
            <div className="flex items-center gap-1.5 px-0.5 text-tiny text-muted-foreground">
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
  entryHasUrdf,
  activeStepArtifactGenerationFile = "",
  stepArtifactGenerationAvailable = true,
  filenameLoadActivity = null,
  selectedStepSourceStatus = null,
  canCopyFileAssetPaths = false,
  onRevealInExplorerView,
  onCopyFileAssetReference,
  fileSheetKind = "",
  fileSheetOpen = false,
  onToggleFileSheet,
  themeEditing = false,
  onToggleThemeEditor,
  navigationAvailable = true
}) {
  const viewerVersion = String(viewerPackage.version || "").trim();
  const discordUrl = normalizeViewerDiscordUrl(import.meta.env?.VIEWER_DISCORD_URL);
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
  const themeToggleLabel = themeEditing ? "Close theme settings" : "Open theme settings";

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
      <Breadcrumb className="min-w-0 overflow-hidden">
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
                  entryHasUrdf={entryHasUrdf}
                  activeStepArtifactGenerationFile={activeStepArtifactGenerationFile}
                  stepArtifactGenerationAvailable={stepArtifactGenerationAvailable}
                  selectedStepSourceStatus={selectedStepSourceStatus}
                  canCopyFileAssetPaths={canCopyFileAssetPaths}
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
                      entryHasUrdf={entryHasUrdf}
                      activeStepArtifactGenerationFile={activeStepArtifactGenerationFile}
                      stepArtifactGenerationAvailable={stepArtifactGenerationAvailable}
                      canCopyFileAssetPaths={canCopyFileAssetPaths}
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
                      entryHasUrdf={entryHasUrdf}
                      activeStepArtifactGenerationFile={activeStepArtifactGenerationFile}
                      stepArtifactGenerationAvailable={stepArtifactGenerationAvailable}
                      selectedStepSourceStatus={selectedStepSourceStatus}
                      canCopyFileAssetPaths={canCopyFileAssetPaths}
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
        <div className="min-w-0" />
      )}

      <div className="min-w-0 flex-1" />

      <TooltipProvider delayDuration={250}>
        <div className="flex shrink-0 items-center gap-1.5">
          <VersionReleaseLink
            version={viewerVersion}
            releaseUrl={releaseUrl}
            releaseCheck={releaseCheck}
          />
          <Button
            asChild
            variant="ghost"
            size="icon-sm"
            aria-label="Join the text-to-cad Discord"
            title="Join the text-to-cad Discord"
            className={topBarIconButtonClasses}
          >
            <a href={discordUrl} target="_blank" rel="noreferrer">
              <DiscordMark className={topBarIconClasses} />
            </a>
          </Button>
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

          {/* A plain toggle for the theme sidebar, matching the file-sheet
              button beside it. Theme selection lives inside the sidebar. */}
          <Button
            type="button"
            variant="ghost"
            size="icon"
            aria-label={themeToggleLabel}
            title={themeToggleLabel}
            aria-pressed={themeEditing}
            onClick={onToggleThemeEditor}
            className={`${topBarIconButtonClasses} ${themeEditing ? activeIconButtonClasses : ""}`}
          >
            <Contrast className={topBarIconClasses} strokeWidth={2} aria-hidden="true" />
            <span className="sr-only">{themeToggleLabel}</span>
          </Button>

          {showFileSheetToggle ? (
            <Button
              type="button"
              variant="ghost"
              size="icon"
              aria-label={fileSheetToggleLabel}
              title={fileSheetToggleLabel}
              aria-pressed={fileSheetOpen && !themeEditing}
              onClick={onToggleFileSheet}
              className={`${topBarIconButtonClasses} ${fileSheetOpen && !themeEditing ? activeIconButtonClasses : ""}`}
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
