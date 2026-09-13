import { cn } from '@core/primitives/styling/browser/cn';

export function PrNumberBadge({ number, className }: { number: number; className?: string }) {
  return (
    <span className={cn('font-sans text-xs text-foreground-muted shrink-0', className)}>
      #{number}
    </span>
  );
}
