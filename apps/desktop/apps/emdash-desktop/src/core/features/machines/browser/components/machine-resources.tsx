import type { ResourceUsageSample } from '@emdash/core/runtimes/resource-usage/api';
import { Box, Field } from '@emdash/ui/react/primitives';

export function ResourceUtilizationRow({ metrics }: { metrics: ResourceUsageSample | null }) {
  return (
    <Field.Root className="flex flex-col gap-3">
      <Field.Label>Resource Utilization</Field.Label>
      <div className="mt-1 grid grid-cols-3 gap-2">
        <ResourceCard
          label="CPU"
          value={metrics ? formatPercent(metrics.cpu.usedPercent) : '—'}
          description="Utilization"
        />
        <ResourceCard
          label="Memory"
          value={metrics ? formatPercent(metrics.memory.usedPercent) : '—'}
          description={
            metrics
              ? `${formatBytes(metrics.memory.usedBytes)} / ${formatBytes(metrics.memory.totalBytes)}`
              : 'Unavailable'
          }
        />
        <ResourceCard
          label="Disk"
          value={metrics ? formatPercent(metrics.disk.usedPercent) : '—'}
          description={
            metrics
              ? `${formatBytes(metrics.disk.usedBytes)} / ${formatBytes(metrics.disk.totalBytes)}`
              : 'Unavailable'
          }
        />
      </div>
    </Field.Root>
  );
}

function ResourceCard({
  label,
  value,
  description,
}: {
  label: string;
  value: string;
  description: string;
}) {
  return (
    <Box surface="sunken" borderRadius="md" padding="2" px="3" className="min-w-0">
      <div className="text-xs text-foreground-muted">{label}</div>
      <div className="mt-1 text-lg font-medium text-foreground tabular-nums">{value}</div>
      <div className="mt-0.5 truncate text-tiny text-foreground-passive tabular-nums">
        {description}
      </div>
    </Box>
  );
}

function formatPercent(value: number): string {
  return `${Math.round(value)}%`;
}

export function formatBytes(bytes: number): string {
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  let value = bytes;
  let unitIndex = 0;
  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024;
    unitIndex += 1;
  }
  const maximumFractionDigits = unitIndex === 0 || value >= 10 ? 0 : 1;
  return `${value.toFixed(maximumFractionDigits)} ${units[unitIndex]}`;
}
