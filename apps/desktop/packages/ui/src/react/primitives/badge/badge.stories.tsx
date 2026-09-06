import { Badge, type BadgeTone, type BadgeVariant } from '@react/primitives/badge';
import { Box } from '@react/primitives/box';
import type { Meta, StoryObj } from '@storybook/react-vite';
import { GitBranchIcon } from 'lucide-react';

const TONES: BadgeTone[] = ['neutral', 'success', 'warning', 'error', 'info'];
const VARIANTS: BadgeVariant[] = ['soft', 'outline'];

const meta: Meta<typeof Badge> = {
  title: 'Primitives/Badge',
  component: Badge,
  parameters: { layout: 'centered' },
  args: {
    children: 'Badge',
  },
};

export default meta;
type Story = StoryObj<typeof Badge>;

export const Default: Story = {};

export const Matrix: Story = {
  render: () => (
    <Box display="flex" flexDirection="column" gap="3">
      {VARIANTS.map((variant) => (
        <Box key={variant} display="flex" alignItems="center" gap="2">
          {TONES.map((tone) => (
            <Badge key={tone} variant={variant} tone={tone}>
              {tone}
            </Badge>
          ))}
        </Box>
      ))}
    </Box>
  ),
};

export const WithIcon: Story = {
  render: () => (
    <Badge>
      <GitBranchIcon />
      main
    </Badge>
  ),
};

export const PolymorphicRender: Story = {
  render: () => (
    <Badge tone="info" render={<a href="#docs" />}>
      Rendered as anchor
    </Badge>
  ),
};

export const CountBadge: Story = {
  render: () => (
    <Box display="flex" alignItems="center" gap="2">
      <span style={{ fontSize: 'var(--em-text-sm)' }}>Local</span>
      <Badge>12</Badge>
    </Box>
  ),
};
