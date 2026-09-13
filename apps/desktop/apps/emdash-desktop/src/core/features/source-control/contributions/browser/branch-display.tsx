import { GitBranch } from 'lucide-react';
import { cn } from '@core/primitives/styling/browser/cn';

interface BranchDisplayProps {
  label: string;
  branchName: string;
  className?: string;
}

export function BranchDisplay({ label, branchName, className }: BranchDisplayProps) {
  return (
    <div
      className={cn(
        'flex w-full items-center gap-2 justify-between p-2 opacity-60 cursor-not-allowed',
        className
      )}
    >
      <div className="flex flex-col gap-0.5 text-left text-sm">
        <span className="text-xs text-foreground-passive">{label}</span>
        <span className="flex items-center gap-1">
          <GitBranch
            absoluteStrokeWidth
            strokeWidth={2}
            className="size-3.5 shrink-0 text-foreground-muted"
          />
          <span>{branchName}</span>
        </span>
      </div>
    </div>
  );
}
