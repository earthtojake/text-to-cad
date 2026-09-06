import { Box } from '@react/primitives/box';
import { Button } from '@react/primitives/button';
import { Popover } from '@react/primitives/popover';
import { Surface } from '@react/primitives/surface/surface';
import { Text } from '@react/primitives/typography/Text';
import type { Meta, StoryObj } from '@storybook/react-vite';
import { useState } from 'react';
import { AnimatedHeight } from '.';

const meta: Meta = {
  title: 'Primitives/AnimatedHeight',
  parameters: { layout: 'centered' },
};

export default meta;
type Story = StoryObj;

const PARAGRAPHS = [
  'AnimatedHeight smoothly transitions its own height whenever the content inside changes size.',
  'Adding more content grows the box with a 0.25s ease transition instead of jumping.',
  'Removing content shrinks it just as smoothly. The initial mount never animates.',
  'Overflow is only clipped while the transition is running, so popovers rendered inside can escape the box at rest.',
];

export const ExpandingCollapsing: Story = {
  render: function ExpandingCollapsingStory() {
    const [count, setCount] = useState(1);
    return (
      <Box display="flex" flexDirection="column" gap="3" style={{ width: '22rem' }}>
        <Box display="flex" gap="2">
          <Button size="sm" onClick={() => setCount((c) => Math.min(c + 1, PARAGRAPHS.length))}>
            Add paragraph
          </Button>
          <Button size="sm" variant="secondary" onClick={() => setCount((c) => Math.max(c - 1, 1))}>
            Remove paragraph
          </Button>
        </Box>
        <Surface level="elevated" style={{ padding: '0.75rem', borderRadius: '0.5rem' }}>
          <AnimatedHeight>
            <Box display="flex" flexDirection="column" gap="2">
              {PARAGRAPHS.slice(0, count).map((paragraph) => (
                <Text key={paragraph} as="p" variant="description">
                  {paragraph}
                </Text>
              ))}
            </Box>
          </AnimatedHeight>
        </Surface>
      </Box>
    );
  },
};

export const OverflowReleased: Story = {
  render: function OverflowReleasedStory() {
    const [expanded, setExpanded] = useState(false);
    return (
      <Box display="flex" flexDirection="column" gap="3" style={{ width: '22rem' }}>
        <Text variant="description" tone="muted">
          Once the height transition settles, overflow is released — the popover below escapes the
          animated box instead of being clipped by it.
        </Text>
        <Surface level="elevated" style={{ padding: '0.75rem', borderRadius: '0.5rem' }}>
          <AnimatedHeight>
            <Box display="flex" flexDirection="column" gap="2" alignItems="flex-start">
              <Button size="sm" variant="secondary" onClick={() => setExpanded((v) => !v)}>
                {expanded ? 'Collapse' : 'Expand'}
              </Button>
              {expanded ? (
                <Popover.Root>
                  <Popover.Trigger render={<Button size="sm">Open popover</Button>} />
                  <Popover.Content>
                    <Text variant="description">This popover escapes the AnimatedHeight box.</Text>
                  </Popover.Content>
                </Popover.Root>
              ) : null}
            </Box>
          </AnimatedHeight>
        </Surface>
      </Box>
    );
  },
};
