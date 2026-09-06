import { Box } from '@react/primitives/box';
import { Spinner, type SpinnerSize } from '@react/primitives/spinner';
import type { Meta, StoryObj } from '@storybook/react-vite';

const SIZES: SpinnerSize[] = ['sm', 'md', 'lg'];

const meta: Meta<typeof Spinner> = {
  title: 'Primitives/Spinner',
  component: Spinner,
  parameters: { layout: 'centered' },
};

export default meta;
type Story = StoryObj<typeof Spinner>;

export const Default: Story = {};

export const Sizes: Story = {
  render: () => (
    <Box display="flex" alignItems="center" gap="4">
      {SIZES.map((size) => (
        <Box key={size} display="flex" flexDirection="column" alignItems="center" gap="2">
          <Spinner size={size} />
          <span style={{ fontSize: 'var(--em-text-xs)', color: 'var(--em-foreground-muted)' }}>
            {size}
          </span>
        </Box>
      ))}
    </Box>
  ),
};

export const InheritsColor: Story = {
  render: () => (
    <Box display="flex" alignItems="center" gap="4">
      <span style={{ color: 'var(--em-foreground-muted)' }}>
        <Spinner />
      </span>
      <span style={{ color: 'var(--em-foreground-success)' }}>
        <Spinner />
      </span>
      <span style={{ color: 'var(--em-foreground-error)' }}>
        <Spinner />
      </span>
    </Box>
  ),
};

export const WithLabel: Story = {
  render: () => (
    <Box display="flex" alignItems="center" gap="2">
      <Spinner size="sm" />
      <span style={{ fontSize: 'var(--em-text-sm)', color: 'var(--em-foreground-muted)' }}>
        Loading workspaces…
      </span>
    </Box>
  ),
};
