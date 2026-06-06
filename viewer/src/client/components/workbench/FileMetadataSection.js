import { useState } from "react";
import { Check, Copy } from "lucide-react";
import { cn } from "@/ui/utils";
import { copyTextToClipboard } from "@/ui/clipboard";
import { FILE_SHEET_SECTION_IDS } from "@/workbench/fileSheetSections";
import { fileMetadataGroupsForEntry } from "@/workbench/fileMetadata";
import {
  FILE_SHEET_FIELD_LABEL_CLASSES,
  FileSheetSection,
  FileSheetSubsection
} from "./FileSheet";

function MetadataCopyButton({ value, label }) {
  const [copied, setCopied] = useState(false);
  const Icon = copied ? Check : Copy;
  const text = String(value || "").trim();
  if (!text) {
    return null;
  }

  return (
    <button
      type="button"
      className={cn(
        "mt-[-0.125rem] inline-flex size-5 shrink-0 items-center justify-center rounded-sm text-muted-foreground transition-colors",
        "hover:bg-sidebar-accent hover:text-sidebar-accent-foreground",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/45"
      )}
      title={`Copy ${label}`}
      aria-label={`Copy ${label}`}
      onClick={async () => {
        try {
          await copyTextToClipboard(text);
          setCopied(true);
          window.setTimeout?.(() => setCopied(false), 1200);
        } catch {
          setCopied(false);
        }
      }}
    >
      <Icon className="size-3" strokeWidth={2} aria-hidden="true" />
    </button>
  );
}

function MetadataValue({
  entry,
  row,
  fileAccessBusyKey = "",
  onOpenFileAsset
}) {
  const text = row.displayValue || row.value;
  const copyValue = String(row.copyValue || "").trim();
  const valueClassName = cn(
    "block min-w-0 break-words text-[11px] leading-4",
    row.mono && "break-all font-mono text-[10px]"
  );

  const withCopyButton = (valueNode) => {
    if (!copyValue) {
      return valueNode;
    }
    return (
      <div className="inline-flex max-w-full items-center gap-1.5 align-top">
        <div className="min-w-0 max-w-full">{valueNode}</div>
        <MetadataCopyButton value={copyValue} label={row.label} />
      </div>
    );
  };

  if (row.action === "open" && row.asset) {
    const busyKey = `${row.asset.fileRef}:${row.asset.asset}`;
    const busy = fileAccessBusyKey === busyKey;
    const canOpen = typeof onOpenFileAsset === "function";

    return withCopyButton(
      <a
        href={row.openUrl || "#"}
        className={cn(
          valueClassName,
          "text-primary underline-offset-4 hover:underline focus-visible:rounded-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/45",
          (!canOpen || busy) && "pointer-events-none text-muted-foreground"
        )}
        title={row.title}
        aria-disabled={!canOpen || busy}
        data-open-url={row.openUrl || undefined}
        onClick={(event) => {
          event.preventDefault();
          if (!canOpen || busy) {
            return;
          }
          onOpenFileAsset(entry, row.asset.asset, row.asset);
        }}
      >
        {busy ? "Opening..." : text}
      </a>
    );
  }

  const content = (
    <span
      className={valueClassName}
      title={row.title}
    >
      {text}
    </span>
  );

  if (!row.href) {
    return withCopyButton(content);
  }

  return withCopyButton(
    <a
      href={row.href}
      download={row.action === "download" ? (row.asset?.filename || true) : undefined}
      className={cn(
        valueClassName,
        "text-primary underline-offset-4 hover:underline focus-visible:rounded-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/45"
      )}
      title={row.title}
    >
      {text}
    </a>
  );
}

export default function FileMetadataSection({
  entry,
  fileDownloadAvailable = false,
  viewerServerInfo = null,
  localFileOpenAvailable = false,
  fileAccessBusyKey = "",
  onOpenFileAsset,
  suppressDynamicStatus = false
}) {
  const groups = fileMetadataGroupsForEntry(entry, {
    includeFileDownloadActions: fileDownloadAvailable && !localFileOpenAvailable,
    includeFileOpenActions: localFileOpenAvailable,
    includePythonSource: localFileOpenAvailable,
    viewerServerInfo,
    suppressDynamicStatus
  });
  if (!groups.length) {
    return null;
  }

  return (
    <FileSheetSection
      value={FILE_SHEET_SECTION_IDS.FILE_METADATA}
      title="Metadata"
      aria-label="File metadata"
    >
      <div>
        {groups.map((group) => (
          <FileSheetSubsection key={group.title} title={group.title} contentClassName="px-3">
            <dl className="space-y-1.5">
              {group.rows.map((row) => (
                <div
                  key={`${group.title}:${row.label}`}
                  className="min-w-0 space-y-0.5 py-0.5"
                >
                  <dt
                    className={cn(FILE_SHEET_FIELD_LABEL_CLASSES, "leading-4")}
                    title={row.label}
                  >
                    {row.label}
                  </dt>
                  <dd className="min-w-0 flex-1 text-sidebar-foreground">
                    <MetadataValue
                      entry={entry}
                      row={row}
                      fileAccessBusyKey={fileAccessBusyKey}
                      onOpenFileAsset={onOpenFileAsset}
                    />
                  </dd>
                </div>
              ))}
            </dl>
          </FileSheetSubsection>
        ))}
      </div>
    </FileSheetSection>
  );
}
