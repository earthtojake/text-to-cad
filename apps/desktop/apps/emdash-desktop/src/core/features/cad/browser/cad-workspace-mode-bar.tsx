import { Button, DropdownMenu, Tooltip } from '@emdash/ui/react/primitives';
import {
  Box,
  Camera,
  Code2,
  FileOutput,
  FolderOpen,
  ListTree,
  Loader2,
  MoreHorizontal,
  Move3d,
  PenLine,
  Plus,
  RefreshCw,
  SlidersHorizontal,
} from 'lucide-react';
import type { ComponentType } from 'react';
import {
  engineeringWorkspaceModeLabel,
  type EngineeringWorkspaceMode,
} from '@core/features/cad/api/browser/cad-engineering-object';

const MODE_ICONS: Partial<Record<EngineeringWorkspaceMode, ComponentType<{ className?: string }>>> =
  {
    '3d': Box,
    '2d': FileOutput,
    drawing: FileOutput,
    source: Code2,
    parameters: SlidersHorizontal,
    files: FolderOpen,
    bom: ListTree,
    motion: Move3d,
    instructions: ListTree,
  };

export function CadWorkspaceModeBar({
  modes,
  activeMode,
  onChange,
  onRefresh,
  onAnnotate,
  onCapture,
  onAddOutput,
  creatingOutput,
}: {
  modes: readonly EngineeringWorkspaceMode[];
  activeMode: EngineeringWorkspaceMode;
  onChange: (mode: EngineeringWorkspaceMode) => void;
  onRefresh?: () => void;
  onAnnotate?: () => void;
  onCapture?: () => void;
  onAddOutput?: (mode: 'drawing') => void;
  creatingOutput?: EngineeringWorkspaceMode | null;
}) {
  const hasCompactOverflowActions = !!(onAnnotate || onCapture);
  return (
    <div className="@container flex h-10 min-w-0 shrink-0 items-center justify-between gap-2 overflow-hidden border-b bg-background px-3">
      <div className="flex min-w-0 flex-1 items-center gap-1.5 overflow-hidden">
        <div
          className="flex min-w-0 items-center gap-0.5"
          role="tablist"
          aria-label="Artifact views"
        >
          {modes.map((mode) => {
            const Icon = MODE_ICONS[mode] ?? Box;
            const active = mode === activeMode;
            return (
              <Button
                key={mode}
                type="button"
                role="tab"
                aria-selected={active}
                aria-label={engineeringWorkspaceModeLabel(mode)}
                variant="ghost"
                size="xs"
                className="min-w-7 gap-1.5 px-2 @max-[520px]:px-1.5"
                onClick={() => onChange(mode)}
              >
                <Icon />
                <span className="@max-[520px]:sr-only">{engineeringWorkspaceModeLabel(mode)}</span>
              </Button>
            );
          })}
        </div>
        {onAddOutput && !modes.includes('drawing') ? (
          <Tooltip.Root>
            <Tooltip.Trigger
              render={
                <Button
                  type="button"
                  size="xs"
                  variant="ghost"
                  aria-label="Create engineering drawing"
                  disabled={creatingOutput === 'drawing'}
                  onClick={() => onAddOutput('drawing')}
                >
                  {creatingOutput === 'drawing' ? <Loader2 className="animate-spin" /> : <Plus />}
                  Drawing
                </Button>
              }
            />
            <Tooltip.Content>Create engineering drawing</Tooltip.Content>
          </Tooltip.Root>
        ) : null}
      </div>
      <div className="flex shrink-0 items-center gap-0.5">
        <div className="hidden items-center gap-0.5 @min-[361px]:flex">
          {onAnnotate ? (
            <Tooltip.Root>
              <Tooltip.Trigger
                render={
                  <Button
                    type="button"
                    size="xs"
                    icon
                    variant="ghost"
                    aria-label="Annotate model"
                    onClick={onAnnotate}
                  >
                    <PenLine />
                  </Button>
                }
              />
              <Tooltip.Content>Draw on the model</Tooltip.Content>
            </Tooltip.Root>
          ) : null}
          {onCapture ? (
            <Tooltip.Root>
              <Tooltip.Trigger
                render={
                  <Button
                    type="button"
                    size="xs"
                    icon
                    variant="ghost"
                    aria-label="Copy screenshot to chat"
                    onClick={onCapture}
                  >
                    <Camera />
                  </Button>
                }
              />
              <Tooltip.Content>Copy screenshot and add it to chat</Tooltip.Content>
            </Tooltip.Root>
          ) : null}
        </div>
        {onRefresh ? (
          <Tooltip.Root>
            <Tooltip.Trigger
              render={
                <Button
                  type="button"
                  size="xs"
                  icon
                  variant="ghost"
                  aria-label="Refresh model"
                  onClick={onRefresh}
                >
                  <RefreshCw />
                </Button>
              }
            />
            <Tooltip.Content>Reload generated geometry</Tooltip.Content>
          </Tooltip.Root>
        ) : null}
      </div>
      {hasCompactOverflowActions ? (
        <div className="hidden shrink-0 @max-[360px]:block">
          <DropdownMenu.Root>
            <DropdownMenu.Trigger
              render={
                <Button
                  type="button"
                  size="xs"
                  icon
                  variant="ghost"
                  aria-label="More artifact actions"
                >
                  <MoreHorizontal />
                </Button>
              }
            />
            <DropdownMenu.Content align="end">
              {onAnnotate ? (
                <DropdownMenu.Item onClick={onAnnotate}>
                  <PenLine className="size-4" />
                  Annotate model
                </DropdownMenu.Item>
              ) : null}
              {onCapture ? (
                <DropdownMenu.Item onClick={onCapture}>
                  <Camera className="size-4" />
                  Copy screenshot to chat
                </DropdownMenu.Item>
              ) : null}
            </DropdownMenu.Content>
          </DropdownMenu.Root>
        </div>
      ) : null}
    </div>
  );
}
