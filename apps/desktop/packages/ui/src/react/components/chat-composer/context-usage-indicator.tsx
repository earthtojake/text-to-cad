import { Button } from '@react/primitives/button';
import { Popover } from '@react/primitives/popover';
import { cx } from '@styles/utilities/cx';
import * as styles from './chat-composer.css';
import { composerThemeScope } from './composer-contract.css';

// ── Data type ─────────────────────────────────────────────────────────────────

export interface ContextUsage {
  used: number;
  size: number;
  cost?: { amount: number; currency: string } | null;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(0)}k`;
  return String(n);
}

function formatCost(cost: { amount: number; currency: string }): string {
  try {
    return new Intl.NumberFormat(undefined, {
      style: 'currency',
      currency: cost.currency,
      minimumFractionDigits: 2,
      maximumFractionDigits: 4,
    }).format(cost.amount);
  } catch {
    return `${cost.amount} ${cost.currency}`;
  }
}

// ── Donut SVG ─────────────────────────────────────────────────────────────────

function ContextDonut({ fraction }: { fraction: number }) {
  const pct = Math.round(fraction * 100);
  return (
    <svg viewBox="0 0 36 36" className={styles.donut} aria-hidden="true">
      <circle className={styles.donutTrack} cx="18" cy="18" r="15" fill="none" strokeWidth="5" />
      <circle
        className={fraction >= 0.9 ? styles.donutProgressWarn : styles.donutProgress}
        cx="18"
        cy="18"
        r="15"
        fill="none"
        strokeWidth="5"
        pathLength={100}
        strokeDasharray={`${pct} 100`}
        strokeLinecap="round"
        transform="rotate(-90 18 18)"
      />
    </svg>
  );
}

// ── Indicator ─────────────────────────────────────────────────────────────────

export function ContextUsageIndicator({
  usage,
  disabled,
}: {
  usage: ContextUsage;
  disabled?: boolean;
}) {
  const fraction = Math.min(1, Math.max(0, usage.used / usage.size));
  const pct = Math.round(fraction * 100);

  return (
    <Popover.Root>
      <Popover.Trigger
        render={
          <Button
            variant="ghost"
            size="xs"
            icon
            disabled={disabled}
            aria-label={`Context window: ${pct}% used`}
          >
            <ContextDonut fraction={fraction} />
          </Button>
        }
      />
      {/* Portaled out of the composer root — must carry the theme-bridge scope. */}
      <Popover.Content className={composerThemeScope} align="end" side="top">
        <Popover.Header>
          <Popover.Title>Context usage</Popover.Title>
        </Popover.Header>
        <div className={styles.usagePopoverBody}>
          <div className={styles.usageStatsRow}>
            <span className={styles.usagePercent}>{pct}%</span>
            <span className={styles.usageTokenCount}>
              {formatTokens(usage.used)} / {formatTokens(usage.size)} Tokens
            </span>
          </div>
          <div className={styles.usageBarTrack} aria-hidden="true">
            <div
              className={cx(styles.usageBarFill, fraction >= 0.9 && styles.usageBarFillWarn)}
              style={{ width: `${pct}%` }}
            />
          </div>
          {usage.cost ? (
            <div className={styles.usageCostRow}>Cost: {formatCost(usage.cost)}</div>
          ) : null}
        </div>
      </Popover.Content>
    </Popover.Root>
  );
}
