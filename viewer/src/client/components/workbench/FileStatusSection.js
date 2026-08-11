import { useEffect, useState } from "react";
import { Check, Copy } from "lucide-react";
import { Badge } from "../ui/badge";
import { Button } from "../ui/button";
import { copyTextToClipboard } from "@/ui/clipboard";
import { cn } from "@/ui/utils";
import {
  FILE_STATUS_LEVELS,
  formatFileStatusItemForAgent,
  fileStatusLevelLabel,
  fileStatusWarningOrErrorItems,
  mostIntenseFileStatusLevel
} from "@/workbench/fileStatusItems";
import { FILE_SHEET_SECTION_IDS } from "@/workbench/fileSheetSections";

const LEVEL_RENDER_META = Object.freeze({
  [FILE_STATUS_LEVELS.ERROR]: {
    badgeVariant: "destructive-outline",
    borderClassName: "border-destructive/70"
  },
  [FILE_STATUS_LEVELS.WARNING]: {
    badgeVariant: "warning-outline",
    borderClassName: "border-amber-500/70"
  },
  [FILE_STATUS_LEVELS.INFO]: {
    badgeVariant: "outline",
    borderClassName: "border-border"
  }
});

const STATUS_COUNT_BADGE_CLASSES = "h-4 min-w-4 self-center rounded-sm px-1 text-[10px] font-medium leading-none";
const STATUS_LEVEL_BADGE_CLASSES = "h-4 self-center rounded-sm px-1.5 py-0 text-[10px] font-medium leading-none";

function renderMetaForLevel(level) {
  return LEVEL_RENDER_META[level] || LEVEL_RENDER_META[FILE_STATUS_LEVELS.INFO];
}

function FileStatusTabContent({ items = [] }) {
  const [expandedItemIds, setExpandedItemIds] = useState(() => new Set());
  const [copiedItemId, setCopiedItemId] = useState("");
  const statusItems = fileStatusWarningOrErrorItems(items);

  useEffect(() => {
    if (!copiedItemId) {
      return undefined;
    }
    const timeout = globalThis.setTimeout(() => setCopiedItemId(""), 1400);
    return () => globalThis.clearTimeout(timeout);
  }, [copiedItemId]);

  if (!statusItems.length) {
    return null;
  }

  const toggleExpanded = (itemId) => {
    setExpandedItemIds((current) => {
      const next = new Set(current);
      if (next.has(itemId)) {
        next.delete(itemId);
      } else {
        next.add(itemId);
      }
      return next;
    });
  };

  const collapseExpandedItem = (itemId) => {
    setExpandedItemIds((current) => {
      if (!current.has(itemId)) {
        return current;
      }
      const next = new Set(current);
      next.delete(itemId);
      return next;
    });
  };

  const handleRowKeyDown = (event, itemId, hasDetails) => {
    if (!hasDetails || (event.key !== "Enter" && event.key !== " ")) {
      return;
    }
    event.preventDefault();
    toggleExpanded(itemId);
  };

  const handleCopyIssue = async (event, item) => {
    event.preventDefault();
    event.stopPropagation();
    try {
      await copyTextToClipboard(formatFileStatusItemForAgent(item));
      setCopiedItemId(item.id);
    } catch {
      setCopiedItemId("");
    }
  };

  return (
    <ul className="space-y-2 py-2 text-xs leading-5">
        {statusItems.map((item) => {
          const itemMeta = renderMetaForLevel(item.level);
          const details = Array.isArray(item.details) ? item.details : [];
          const hasDetails = details.length > 0;
          const expanded = expandedItemIds.has(item.id);
          return (
            <li
              key={item.id}
              className={cn("min-w-0 border-l-2", itemMeta.borderClassName)}
            >
              <div
                role={hasDetails ? "button" : undefined}
                tabIndex={hasDetails ? 0 : undefined}
                className={cn(
                  "block min-w-0 rounded-md px-2 py-1 text-left",
                  hasDetails && "w-full cursor-pointer hover:bg-sidebar-accent/60 hover:text-sidebar-accent-foreground",
                  !hasDetails && "w-full"
                )}
                onClick={() => {
                  if (hasDetails) {
                    toggleExpanded(item.id);
                  }
                }}
                onKeyDown={(event) => handleRowKeyDown(event, item.id, hasDetails)}
                aria-expanded={hasDetails ? expanded : undefined}
              >
                <div className="flex min-w-0 items-center gap-2">
                  <Badge variant={itemMeta.badgeVariant} className={cn("shrink-0", STATUS_LEVEL_BADGE_CLASSES)}>
                    {fileStatusLevelLabel(item.level)}
                  </Badge>
                  <div className="min-w-0 flex-1 truncate font-medium leading-4 text-sidebar-foreground" title={item.title}>{item.title}</div>
                  <span className="ml-auto inline-flex h-5 shrink-0 items-center">
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon-xs"
                      className="size-5 rounded-sm text-muted-foreground hover:text-sidebar-foreground"
                      onClick={(event) => handleCopyIssue(event, item)}
                      aria-label={copiedItemId === item.id ? "Copied issue" : "Copy issue for agent"}
                      title={copiedItemId === item.id ? "Copied" : "Copy issue for agent"}
                    >
                      {copiedItemId === item.id ? (
                        <Check className="size-3" strokeWidth={2.25} aria-hidden="true" />
                      ) : (
                        <Copy className="size-3" strokeWidth={2.1} aria-hidden="true" />
                      )}
                    </Button>
                  </span>
                </div>
                {item.message ? (
                  <div className="mt-1 line-clamp-2 min-w-0 break-words text-[11px] font-normal leading-4 text-muted-foreground">
                    {item.message}
                  </div>
                ) : null}
              </div>
              {hasDetails && expanded ? (
                <div className="mt-2 space-y-2 pl-2">
                  <dl className="space-y-1 text-[11px] leading-4">
                    {details.map((detailItem, index) => (
                      <div key={`${item.id}:${detailItem.label}:${index}`} className="min-w-0">
                        <dt className="text-muted-foreground">{detailItem.label}</dt>
                        <dd className={cn(
                          "min-w-0 break-words text-sidebar-foreground",
                          detailItem.mono && "break-all font-mono text-[10px] leading-4"
                        )}>
                          {detailItem.value}
                        </dd>
                      </div>
                    ))}
                  </dl>
                  <Button
                    type="button"
                    variant="ghost"
                    size="xs"
                    className="h-auto rounded-sm px-0 py-0 text-[11px] font-medium text-muted-foreground hover:bg-transparent hover:text-sidebar-foreground"
                    onClick={(event) => {
                      event.preventDefault();
                      event.stopPropagation();
                      collapseExpandedItem(item.id);
                    }}
                  >
                    Collapse
                  </Button>
                </div>
              ) : null}
            </li>
          );
        })}
      </ul>
  );
}

// Build the "Issues" tab descriptor, or null when there are no warnings/errors.
export function buildFileStatusTab(items = []) {
  const statusItems = fileStatusWarningOrErrorItems(items);
  if (!statusItems.length) {
    return null;
  }
  const headerMeta = renderMetaForLevel(mostIntenseFileStatusLevel(statusItems));
  return {
    id: FILE_SHEET_SECTION_IDS.FILE_STATUS,
    title: (
      <span className="flex min-w-0 items-center gap-1.5">
        <span>Issues</span>
        <Badge variant={headerMeta.badgeVariant} className={STATUS_COUNT_BADGE_CLASSES}>{statusItems.length}</Badge>
      </span>
    ),
    content: <FileStatusTabContent items={items} />
  };
}
