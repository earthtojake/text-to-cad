import { CollectionToolbar } from '@emdash/ui/react/patterns';
import { Button } from '@emdash/ui/react/primitives';
import { Plus, RefreshCw } from 'lucide-react';
import React from 'react';
import { useSearchFocusHotkeys } from '@core/primitives/keybindings/browser';

type McpToolbarProps = {
  search: string;
  onSearchChange: (search: string) => void;
  onRefresh: () => void;
  isRefreshing: boolean;
  onAddCustom: () => void;
};

export function McpToolbar({
  search,
  onSearchChange,
  onRefresh,
  isRefreshing,
  onAddCustom,
}: McpToolbarProps) {
  const searchRef = useSearchFocusHotkeys();
  return (
    <CollectionToolbar
      ref={searchRef}
      searchValue={search}
      onSearchValueChange={onSearchChange}
      searchPlaceholder="Search servers…"
      actions={
        <>
          <Button
            variant="secondary"
            icon
            onClick={onRefresh}
            disabled={isRefreshing}
            aria-label="Refresh providers"
          >
            <RefreshCw
              className={`h-4 w-4 text-foreground-muted ${isRefreshing ? 'animate-spin' : ''}`}
            />
          </Button>
          <Button variant="primary" onClick={onAddCustom}>
            <Plus className="size-4" />
            Custom MCP
          </Button>
        </>
      }
    />
  );
}
