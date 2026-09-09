import type { Meta, StoryObj } from '@storybook/react-vite';
import { Pill, type PillVariant } from './pill';

const VARIANTS: Array<{ label: string; variant: PillVariant }> = [
  { label: 'Neutral', variant: 'neutral' },
  { label: 'Success', variant: 'success' },
  { label: 'Warning', variant: 'warning' },
  { label: 'Error', variant: 'error' },
  { label: 'Info', variant: 'info' },
];

const meta: Meta<typeof Pill> = {
  title: 'Components/Pill',
  component: Pill,
  parameters: { layout: 'centered' },
  args: {
    variant: 'neutral',
    dot: true,
    children: 'Status',
  },
};
export default meta;
type Story = StoryObj<typeof Pill>;

export const Default: Story = {
  name: 'Default',
};

export const Variants: Story = {
  name: 'Variants',
  render: () => (
    <div style={{ display: 'flex', alignItems: 'flex-start', gap: '1rem' }}>
      {VARIANTS.map(({ label, variant }) => (
        <div
          key={variant}
          style={{
            display: 'flex',
            minWidth: '6rem',
            flexDirection: 'column',
            alignItems: 'center',
            gap: '0.5rem',
          }}
        >
          <Pill variant={variant} dot>
            {label}
          </Pill>
          <span
            style={{
              fontSize: 'var(--em-text-xs)',
              color: 'var(--em-foreground-muted)',
            }}
          >
            {variant}
          </span>
        </div>
      ))}
    </div>
  ),
};

export const WithoutDot: Story = {
  name: 'Without dot',
  render: () => (
    <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
      {VARIANTS.map(({ label, variant }) => (
        <Pill key={variant} variant={variant}>
          {label}
        </Pill>
      ))}
    </div>
  ),
};

export const PulsingDot: Story = {
  name: 'Pulsing dot',
  render: () => (
    <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
      {VARIANTS.map(({ label, variant }) => (
        <Pill key={variant} variant={variant} dot pulsing>
          {label}
        </Pill>
      ))}
    </div>
  ),
};
