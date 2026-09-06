import { Box } from '@react/primitives/box';
import type { Meta, StoryObj } from '@storybook/react-vite';
import { cx } from '@styles/utilities/cx';
import { card } from '@styles/recipes/card.css';
import { row, stack } from '@styles/utilities/layout.css';

const meta = {
  title: 'Primitives/Box',
  component: Box,
  parameters: { layout: 'padded' },
} satisfies Meta<typeof Box>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  render: () => (
    <Box display="flex" flexDirection="column" gap="4" padding="4">
      <Box background="surface" borderRadius="md" padding="3">
        Box with sprinkles
      </Box>
      <Box as="section" display="flex" alignItems="center" gap="2">
        <Box background="surfaceEmphasis" borderRadius="sm" padding="2" fontSize="sm">
          Item A
        </Box>
        <Box background="surfaceEmphasis" borderRadius="sm" padding="2" fontSize="sm">
          Item B
        </Box>
      </Box>
    </Box>
  ),
};

export const WithRecipe: Story = {
  render: () => (
    <Box className={cx(stack)} gap="3" padding="4">
      <Box className={cx(card())} padding="3">
        Card via recipe + Box
      </Box>
      <Box className={cx(card({ level: 'elevated' }), row)} gap="2" padding="3">
        Elevated card with row layout
      </Box>
    </Box>
  ),
};

export const PolymorphicAs: Story = {
  render: () => (
    <Box as="ul" display="flex" flexDirection="column" gap="2" padding="4">
      <Box as="li" background="surfaceEmphasis" padding="2" borderRadius="sm" fontSize="sm">
        List item 1
      </Box>
      <Box as="li" background="surfaceEmphasis" padding="2" borderRadius="sm" fontSize="sm">
        List item 2
      </Box>
    </Box>
  ),
};

/** surface prop applies .surface-<value> class (cascade scope) + background: var(--em-surface). */
export const Surfaces: Story = {
  render: () => (
    <Box display="flex" flexDirection="column" gap="3" padding="4">
      {(['sunken', 'base', 'base-emphasis', 'elevated', 'elevated-emphasis', 'paper'] as const).map(
        (level) => (
          <Box
            key={level}
            surface={level}
            borderRadius="md"
            padding="3"
            display="flex"
            alignItems="center"
            gap="3"
          >
            <Box fontSize="xs" color="foregroundMuted" style={{ minWidth: '9rem' }}>
              {level}
            </Box>
            <Box surface="emphasis" borderRadius="sm" padding="2" fontSize="sm">
              emphasis card
            </Box>
          </Box>
        )
      )}
      <Box display="flex" gap="3">
        {(['destructive', 'warning', 'info'] as const).map((status) => (
          <Box key={status} surface={status} borderRadius="md" padding="3" fontSize="sm" flex="1">
            {status}
          </Box>
        ))}
      </Box>
    </Box>
  ),
};
