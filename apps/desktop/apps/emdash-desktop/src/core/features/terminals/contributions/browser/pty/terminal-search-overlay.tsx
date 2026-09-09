import { Button, Input } from '@emdash/ui/react/primitives';
import { ChevronDown, ChevronUp, Search, X } from 'lucide-react';
import React, { type RefObject } from 'react';
import type { TerminalSearchStatus } from '@core/features/terminals/api/browser/pty/use-terminal-search';
import { terminalSearchScope } from '@core/features/workbench/contributions/scopes';
import { cn } from '@core/primitives/styling/browser/cn';
import type { ViewScopeImpl } from '@core/primitives/view-scopes/api';
import { useViewScope } from '@core/primitives/view-scopes/react';

interface Props {
  sessionId: string;
  isOpen: boolean;
  fullWidth?: boolean;
  searchQuery: string;
  searchStatus: TerminalSearchStatus;
  searchInputRef: RefObject<HTMLInputElement | null>;
  onQueryChange: (value: string) => void;
  onStep: (direction: 'next' | 'prev') => void;
  onFind: () => void;
  onClose: () => void;
}

export function TerminalSearchOverlay({
  sessionId,
  isOpen,
  fullWidth = false,
  searchQuery,
  searchStatus,
  searchInputRef,
  onQueryChange,
  onStep,
  onFind,
  onClose,
}: Props) {
  const implementation = {
    'terminal.find': () => ({ execute: onFind }),
    'terminalSearch.close': () => ({ execute: onClose }),
  } satisfies ViewScopeImpl<typeof terminalSearchScope>;
  const { attachRef } = useViewScope(terminalSearchScope({ sessionId }), implementation);

  if (!isOpen) return null;

  return (
    <div
      ref={attachRef}
      className={cn(
        'absolute top-3 z-20 flex items-center gap-1 rounded-md border border-border bg-background/95 p-1.5 shadow-lg backdrop-blur',
        fullWidth ? 'left-3 right-3 w-auto max-w-none' : 'right-3 w-[min(28rem,calc(100%-1.5rem))]'
      )}
    >
      <div className="relative min-w-0 flex-1">
        <Search className="pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-foreground-muted" />
        <Input
          ref={searchInputRef}
          value={searchQuery}
          onChange={(event) => onQueryChange(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter') {
              event.preventDefault();
              onStep(event.shiftKey ? 'prev' : 'next');
              return;
            }
          }}
          placeholder="Find in terminal..."
          className="h-8 min-w-0 border-0 bg-transparent pr-2 pl-8 text-xs shadow-none focus-visible:ring-0"
          aria-label="Find in terminal"
        />
      </div>
      <div className="ml-auto flex shrink-0 items-center gap-0.5">
        <span className="min-w-10 shrink-0 px-1 text-center text-tiny text-foreground-muted">
          {searchQuery ? `${searchStatus.currentIndex}/${searchStatus.total}` : '0/0'}
        </span>
        <Button
          type="button"
          variant="ghost"
          size="xs"
          icon
          onClick={() => onStep('prev')}
          disabled={!searchQuery || searchStatus.total === 0}
          className="shrink-0 text-foreground-muted"
          aria-label="Previous terminal match"
        >
          <ChevronUp className="size-3.5" />
        </Button>
        <Button
          type="button"
          variant="ghost"
          size="xs"
          icon
          onClick={() => onStep('next')}
          disabled={!searchQuery || searchStatus.total === 0}
          className="shrink-0 text-foreground-muted"
          aria-label="Next terminal match"
        >
          <ChevronDown className="size-3.5" />
        </Button>
        <Button
          type="button"
          variant="ghost"
          size="xs"
          icon
          onClick={onClose}
          className="shrink-0 text-foreground-muted"
          aria-label="Close terminal search"
        >
          <X className="size-3.5" />
        </Button>
      </div>
    </div>
  );
}
