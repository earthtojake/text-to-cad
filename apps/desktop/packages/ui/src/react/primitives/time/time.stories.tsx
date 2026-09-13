import { Box } from '@react/primitives/box';
import { AbsoluteTime } from '@react/primitives/time/absolute-time';
import { RelativeTime } from '@react/primitives/time/relative-time';
import type { Meta, StoryObj } from '@storybook/react-vite';

const meta: Meta = {
  title: 'Primitives/Time',
  parameters: { layout: 'centered' },
};

export default meta;
type Story = StoryObj;

const minutesAgo = (n: number) => new Date(Date.now() - n * 60_000);

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <Box display="flex" alignItems="center" gap="4">
      <span
        style={{
          width: '16rem',
          fontSize: 'var(--em-text-xs)',
          color: 'var(--em-foreground-muted)',
        }}
      >
        {label}
      </span>
      {children}
    </Box>
  );
}

export const Absolute: Story = {
  render: () => (
    <Box display="flex" flexDirection="column" gap="2">
      <Row label="Current year (no year shown)">
        <AbsoluteTime value={new Date()} />
      </Row>
      <Row label="includeYear">
        <AbsoluteTime value={new Date()} includeYear />
      </Row>
      <Row label="Past year (year auto-included)">
        <AbsoluteTime value="2023-06-15 08:30:00" />
      </Row>
      <Row label="Bare SQLite timestamp (parsed as UTC)">
        <AbsoluteTime value="2023-06-15 08:30:00" includeYear />
      </Row>
      <Row label="Unparseable input">
        <AbsoluteTime value="not a date" />
      </Row>
    </Box>
  ),
};

export const Relative: Story = {
  render: () => (
    <Box display="flex" flexDirection="column" gap="2">
      <Row label="Just now">
        <RelativeTime value={minutesAgo(0)} />
      </Row>
      <Row label="5 minutes ago">
        <RelativeTime value={minutesAgo(5)} />
      </Row>
      <Row label="3 days ago">
        <RelativeTime value={minutesAgo(60 * 24 * 3)} />
      </Row>
      <Row label="Unparseable input">
        <RelativeTime value="" />
      </Row>
    </Box>
  ),
};

export const RelativeCompact: Story = {
  render: () => (
    <Box display="flex" flexDirection="column" gap="2">
      <Row label="Under a minute → now">
        <RelativeTime value={minutesAgo(0)} compact />
      </Row>
      <Row label="Minutes → 5m">
        <RelativeTime value={minutesAgo(5)} compact />
      </Row>
      <Row label="Hours → 3h">
        <RelativeTime value={minutesAgo(60 * 3)} compact />
      </Row>
      <Row label="Days → 3d">
        <RelativeTime value={minutesAgo(60 * 24 * 3)} compact />
      </Row>
      <Row label="Months → 2mo">
        <RelativeTime value={minutesAgo(60 * 24 * 65)} compact />
      </Row>
      <Row label="Years → 1y">
        <RelativeTime value={minutesAgo(60 * 24 * 400)} compact />
      </Row>
      <Row label="With muted ago suffix">
        <RelativeTime value={minutesAgo(60 * 3)} compact ago />
      </Row>
      <Row label='ago suppressed while "now"'>
        <RelativeTime value={minutesAgo(0)} compact ago />
      </Row>
    </Box>
  ),
};
