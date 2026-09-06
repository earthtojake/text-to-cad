import { CollectionToolbar } from '@emdash/ui/react/patterns';
import { Button } from '@emdash/ui/react/primitives';
import { Plus, RefreshCw } from 'lucide-react';
import React from 'react';
import { useSearchFocusHotkeys } from '@core/primitives/keybindings/browser';

type SkillsToolbarProps = {
  searchQuery: string;
  onSearchQueryChange: (query: string) => void;
  onRefresh: () => void;
  isRefreshing: boolean;
  onCreateSkill: () => void;
};

export function SkillsToolbar({
  searchQuery,
  onSearchQueryChange,
  onRefresh,
  isRefreshing,
  onCreateSkill,
}: SkillsToolbarProps) {
  const searchRef = useSearchFocusHotkeys();
  return (
    <CollectionToolbar
      ref={searchRef}
      searchValue={searchQuery}
      onSearchValueChange={onSearchQueryChange}
      searchPlaceholder="Search skills…"
      actions={
        <>
          <Button
            variant="secondary"
            icon
            onClick={onRefresh}
            disabled={isRefreshing}
            aria-label="Refresh catalog"
          >
            <RefreshCw
              className={`h-4 w-4 text-foreground-muted ${isRefreshing ? 'animate-spin' : ''}`}
            />
          </Button>
          <Button variant="primary" onClick={onCreateSkill}>
            <Plus className="size-4" />
            New Skill
          </Button>
        </>
      }
    />
  );
}
