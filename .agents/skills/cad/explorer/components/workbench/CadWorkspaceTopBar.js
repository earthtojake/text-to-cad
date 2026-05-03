import { Fragment } from "react";
import { LoaderCircle, Palette, ShoppingCart, SlidersHorizontal } from "lucide-react";
import { normalizeExplorerGithubUrl } from "../../lib/explorerConfig.mjs";
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator
} from "@/components/ui/breadcrumb";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger
} from "@/components/ui/dropdown-menu";
import { SidebarTrigger, useSidebar } from "@/components/ui/sidebar";

function pathSegmentsForEntry(entry, fallbackLabel) {
  if (!entry) {
    return [fallbackLabel];
  }

  const sourcePath = String(entry.source?.path || entry.step?.path || entry.id || "").trim();
  const segments = sourcePath
    ? sourcePath.replace(/\\/g, "/").split("/").filter(Boolean)
    : [];

  if (!segments.length) {
    return [fallbackLabel];
  }

  return [
    ...segments.slice(0, -1),
    fallbackLabel
  ];
}

function collapsedBreadcrumbSegments(segments) {
  if (segments.length <= 3) {
    return segments.map((segment) => ({ type: "segment", label: segment }));
  }

  return [
    { type: "segment", label: segments[0] },
    { type: "ellipsis", label: "...", segments: segments.slice(1, -2) },
    ...segments.slice(-2).map((segment) => ({ type: "segment", label: segment }))
  ];
}

function fileSheetLabel(fileSheetKind) {
  if (fileSheetKind === "dxf") {
    return "DXF sheet";
  }
  if (fileSheetKind === "urdf") {
    return "URDF sheet";
  }
  if (fileSheetKind === "stepAssembly") {
    return "assembly sheet";
  }
  return "file sheet";
}

function BreadcrumbEllipsisDropdown({ segments, title }) {
  const hiddenSegments = Array.isArray(segments) ? segments.filter(Boolean) : [];
  const menuTitle = hiddenSegments.join(" / ") || title;

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
      <DropdownMenuContent align="start" sideOffset={6} className="max-w-72">
        {hiddenSegments.map((segment, index) => (
          <DropdownMenuItem
            key={`${segment}:${index}`}
            className="max-w-64 text-xs"
            title={segment}
          >
            <span className="block min-w-0 truncate">{segment}</span>
          </DropdownMenuItem>
        ))}
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

export default function CadWorkspaceTopBar({
  previewMode,
  lookMenuOpen,
  sidebarLabelForEntry,
  selectedEntry,
  setLookMenuOpen,
  filenameLoadActivity = null,
  fileSheetKind = "",
  fileSheetOpen = false,
  onToggleFileSheet,
  onOpenOttoAuth
}) {
  const { isMobile, state: sidebarState } = useSidebar();

  if (previewMode) {
    return null;
  }

  const selectedFileLabel = selectedEntry ? sidebarLabelForEntry(selectedEntry) : "Select a file";
  const selectedFileTitle = selectedEntry
    ? String(selectedEntry.source?.path || selectedEntry.step?.path || selectedEntry.id || selectedFileLabel)
    : selectedFileLabel;
  const breadcrumbSegments = pathSegmentsForEntry(selectedEntry, selectedFileLabel);
  const breadcrumbItems = collapsedBreadcrumbSegments(breadcrumbSegments);
  const activeIconButtonClasses = "bg-accent text-accent-foreground";
  const showFileSheetToggle = !!fileSheetKind && typeof onToggleFileSheet === "function";
  const lookSheetToggleLabel = lookMenuOpen
    ? "Collapse explorer settings"
    : "Expand explorer settings";
  const fileSheetToggleLabel = fileSheetOpen
    ? `Collapse ${fileSheetLabel(fileSheetKind)}`
    : `Expand ${fileSheetLabel(fileSheetKind)}`;
  const showTopBarSidebarTrigger = isMobile || sidebarState !== "expanded";
  const githubUrl = normalizeExplorerGithubUrl(import.meta.env?.EXPLORER_GITHUB_URL);

  return (
    <header
      className="cad-glass-surface pointer-events-auto flex h-11 shrink-0 items-center gap-2 border-b border-sidebar-border px-2 text-sidebar-foreground"
    >
      {showTopBarSidebarTrigger ? (
        <SidebarTrigger
          title="Toggle CAD Explorer"
          aria-label="Toggle CAD Explorer"
        />
      ) : null}

      <Breadcrumb className="min-w-0 flex-1">
        <BreadcrumbList className="min-w-0 flex-nowrap gap-1.5 text-xs sm:gap-1.5">
          {breadcrumbItems.map((item, index) => (
            <Fragment key={`${item.type}:${item.label}:${index}`}>
              <BreadcrumbItem className="min-w-0">
                {item.type === "ellipsis" ? (
                  <BreadcrumbEllipsisDropdown segments={item.segments} title={selectedFileTitle} />
                ) : index < breadcrumbItems.length - 1 ? (
                  <BreadcrumbLink asChild className="block max-w-32 truncate text-xs font-medium">
                    <span title={selectedFileTitle}>{item.label}</span>
                  </BreadcrumbLink>
                ) : (
                  <BreadcrumbPage
                    className="flex min-w-0 max-w-[min(36rem,55vw)] items-center gap-2 text-xs font-medium"
                    title={selectedFileTitle}
                  >
                    <span className="min-w-0 truncate">{item.label}</span>
                    <FilenameLoadStatus activity={filenameLoadActivity} />
                  </BreadcrumbPage>
                )}
              </BreadcrumbItem>
              {index < breadcrumbItems.length - 1 ? (
                <BreadcrumbSeparator className="text-muted-foreground/60" />
              ) : null}
            </Fragment>
          ))}
        </BreadcrumbList>
      </Breadcrumb>

      <div className="flex shrink-0 items-center gap-0.5">
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

        <Button
          type="button"
          variant="ghost"
          size="icon-sm"
          aria-label="Buy parts now"
          title="Buy parts now"
          onClick={onOpenOttoAuth}
          className={topBarIconButtonClasses}
        >
          <ShoppingCart className={topBarIconClasses} strokeWidth={2} aria-hidden="true" />
        </Button>

        <Button
          type="button"
          variant="ghost"
          size="icon-sm"
          aria-label={lookSheetToggleLabel}
          title={lookSheetToggleLabel}
          aria-pressed={lookMenuOpen}
          onClick={() => {
            setLookMenuOpen((current) => !current);
          }}
          className={`${topBarIconButtonClasses} ${lookMenuOpen ? activeIconButtonClasses : ""}`}
        >
          <Palette className={topBarIconClasses} strokeWidth={2} aria-hidden="true" />
        </Button>

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
    </header>
  );
}
