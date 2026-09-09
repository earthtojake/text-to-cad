import type { Meta, StoryObj } from '@storybook/react-vite';
import { Loader2Icon } from 'lucide-react';
import * as React from 'react';
import { SegmentedSpinnerIcon } from '.';

const meta: Meta<typeof SegmentedSpinnerIcon> = {
  title: 'Primitives/SegmentedSpinnerIcon',
  component: SegmentedSpinnerIcon,
  parameters: { layout: 'centered' },
  args: {
    size: '2rem',
  },
};
export default meta;
type Story = StoryObj<typeof SegmentedSpinnerIcon>;

// ── Single default ─────────────────────────────────────────────────────────────

export const Default: Story = {
  name: 'Default',
};

// ── Size scale ─────────────────────────────────────────────────────────────────

const SIZES: Array<{ label: string; size: string }> = [
  { label: '12px (xs)', size: '0.75rem' },
  { label: '14px (sm)', size: '0.875rem' },
  { label: '16px (base)', size: '1rem' },
  { label: '20px (lg)', size: '1.25rem' },
  { label: '24px (xl)', size: '1.5rem' },
  { label: '32px (2xl)', size: '2rem' },
];

export const Sizes: Story = {
  name: 'Sizes',
  render: () => (
    <div style={{ display: 'flex', alignItems: 'center', gap: '1.5rem' }}>
      {SIZES.map(({ label, size }) => (
        <div
          key={label}
          style={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            gap: '0.5rem',
          }}
        >
          <SegmentedSpinnerIcon size={size} />
          <span
            style={{
              fontSize: 'var(--em-text-xs)',
              color: 'var(--em-foreground-muted)',
              fontFamily: 'var(--em-font-mono)',
              whiteSpace: 'nowrap',
            }}
          >
            {label}
          </span>
        </div>
      ))}
    </div>
  ),
};

// ── Color inheritance ──────────────────────────────────────────────────────────

const COLORS: Array<{ label: string; color: string }> = [
  { label: 'foreground', color: 'var(--em-foreground)' },
  { label: 'foreground-muted', color: 'var(--em-foreground-muted)' },
  { label: 'foreground-passive', color: 'var(--em-foreground-passive)' },
  { label: 'foreground-success', color: 'var(--em-foreground-success)' },
  { label: 'foreground-error', color: 'var(--em-foreground-error)' },
  { label: 'foreground-warning', color: 'var(--em-foreground-warning)' },
];

export const Colors: Story = {
  name: 'Colors — inherits currentColor',
  render: () => (
    <div style={{ display: 'flex', alignItems: 'center', gap: '1.5rem' }}>
      {COLORS.map(({ label, color }) => (
        <div
          key={label}
          style={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            gap: '0.5rem',
            color,
          }}
        >
          <SegmentedSpinnerIcon size="1.5rem" />
          <span
            style={{
              fontSize: 'var(--em-text-xs)',
              color: 'var(--em-foreground-muted)',
              fontFamily: 'var(--em-font-mono)',
              whiteSpace: 'nowrap',
            }}
          >
            {label}
          </span>
        </div>
      ))}
    </div>
  ),
};

// ── Comparison with Loader2Icon ────────────────────────────────────────────────
//
// Inline keyframes for the rotating Loader2 so the story doesn't depend on the
// stepped-loader's internal CSS class. We only want a visual comparison.

const spinStyle: React.CSSProperties = {
  animation: 'spin 1s linear infinite',
};

export const VsLucideLoader: Story = {
  name: 'vs Lucide Loader2Icon (rotating)',
  render: () => (
    <>
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
      <div style={{ display: 'flex', alignItems: 'center', gap: '3rem' }}>
        <div
          style={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            gap: '0.75rem',
            color: 'var(--em-foreground-muted)',
          }}
        >
          <Loader2Icon width={32} height={32} style={spinStyle} />
          <span
            style={{
              fontSize: 'var(--em-text-xs)',
              color: 'var(--em-foreground-muted)',
              fontFamily: 'var(--em-font-mono)',
            }}
          >
            Loader2Icon + rotate
          </span>
        </div>
        <div
          style={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            gap: '0.75rem',
            color: 'var(--em-foreground-muted)',
          }}
        >
          <SegmentedSpinnerIcon size="2rem" />
          <span
            style={{
              fontSize: 'var(--em-text-xs)',
              color: 'var(--em-foreground-muted)',
              fontFamily: 'var(--em-font-mono)',
            }}
          >
            SegmentedSpinnerIcon
          </span>
        </div>
      </div>
    </>
  ),
};

// ── Inline in text ─────────────────────────────────────────────────────────────

export const InlineWithText: Story = {
  name: 'Inline with text',
  render: () => (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
      {(['var(--em-text-xs)', 'var(--em-text-sm)', 'var(--em-text-base)'] as const).map(
        (fontSize) => (
          <div
            key={fontSize}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '0.375rem',
              fontSize,
              color: 'var(--em-foreground-muted)',
            }}
          >
            <SegmentedSpinnerIcon />
            <span>Loading…</span>
            <span
              style={{
                marginLeft: '0.5rem',
                fontFamily: 'var(--em-font-mono)',
                color: 'var(--em-foreground-passive)',
              }}
            >
              ({fontSize})
            </span>
          </div>
        )
      )}
    </div>
  ),
};
