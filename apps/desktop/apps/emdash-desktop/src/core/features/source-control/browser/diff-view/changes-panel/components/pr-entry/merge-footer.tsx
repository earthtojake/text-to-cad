import { Button, Checkbox, SplitButton } from '@emdash/ui/react/primitives';
import {
  AlertTriangle,
  CheckCircle2,
  GitMerge,
  HelpCircle,
  Loader2,
  XCircle,
  type LucideIcon,
} from 'lucide-react';
import { useState } from 'react';
import { cn } from '@core/primitives/styling/browser/cn';
import { type MergeSeverity, type MergeUiState } from './merge-ui-state';

/** A selectable action for the merge split button: label plus its own callback. */
export type MergeAction = {
  value: string;
  label: string;
  description?: string;
  action: () => void;
};

const severityConfig: Record<MergeSeverity, SeverityConfig> = {
  success: { icon: CheckCircle2, iconClass: 'text-foreground-success' },
  warning: { icon: AlertTriangle, iconClass: 'text-foreground-warning' },
  error: { icon: XCircle, iconClass: 'text-foreground-error' },
  neutral: { icon: HelpCircle, iconClass: 'text-foreground-passive' },
};

type SeverityConfig = { icon: LucideIcon; iconClass: string };

export function MergeFooter({
  uiState,
  mergeActions,
  isMerging,
  isMarkingReady,
  bypassRequirements,
  onMarkReady,
  onBypassRequirementsChange,
}: {
  uiState: MergeUiState;
  mergeActions: MergeAction[];
  isMerging: boolean;
  isMarkingReady: boolean;
  bypassRequirements: boolean;
  onMarkReady: () => void;
  onBypassRequirementsChange: (checked: boolean) => void;
}) {
  const isDraft = uiState.kind === 'draft';
  const [selectedMergeId, setSelectedMergeId] = useState<string | undefined>(undefined);
  const mergeDisabled =
    !isMerging && !uiState.canMerge && (!uiState.canBypassRequirements || !bypassRequirements);
  const bypassEnabled = uiState.canBypassRequirements && bypassRequirements;
  const { icon: MergeStatusIcon, iconClass } =
    severityConfig[bypassEnabled ? 'warning' : uiState.severity];
  const mergeStatusTitle = bypassEnabled ? 'Bypass requirements enabled' : uiState.title;

  return (
    <div className="flex shrink-0 flex-col gap-2 border-t border-border px-3 py-2.5">
      <div className="flex items-center justify-between gap-1.5">
        <div className="flex min-w-0 items-center gap-1.5">
          <MergeStatusIcon className={cn('size-4 shrink-0', iconClass)} />
          <p className="truncate text-sm leading-tight text-foreground">{mergeStatusTitle}</p>
        </div>
        <div className="flex items-center gap-1.5">
          {isDraft ? (
            <Button
              variant="secondary"
              size="xs"
              onClick={onMarkReady}
              disabled={isMarkingReady}
              aria-label={isMarkingReady ? 'Marking ready...' : 'Mark ready'}
            >
              {isMarkingReady && <Loader2 className="size-3 animate-spin" aria-hidden />}
              Mark ready
            </Button>
          ) : (
            <SplitButton
              size="xs"
              variant="secondary"
              loading={isMerging}
              loadingLabel="Merging..."
              icon={<GitMerge className="size-3" />}
              options={mergeActions.map(({ value, label, description }) => ({
                id: value,
                label,
                description,
              }))}
              selectedId={selectedMergeId}
              onSelectedChange={setSelectedMergeId}
              commitOnSelect={false}
              onAction={(id) => mergeActions.find((a) => a.value === id)?.action()}
              disabled={mergeDisabled}
            />
          )}
        </div>
      </div>
      {uiState.canBypassRequirements && (
        <label className="flex cursor-pointer items-start gap-2 text-xs leading-snug text-foreground-error">
          <Checkbox
            className="mt-px"
            checked={bypassRequirements}
            onCheckedChange={(checked) => onBypassRequirementsChange(Boolean(checked))}
          />
          <span>Merge without waiting for requirements to be met (bypass rules)</span>
        </label>
      )}
    </div>
  );
}
