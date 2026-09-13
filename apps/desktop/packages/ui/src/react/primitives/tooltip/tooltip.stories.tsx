import { Box } from '@react/primitives/box';
import { Button } from '@react/primitives/button';
import { Kbd, KbdGroup } from '@react/primitives/kbd';
import type { Meta, StoryObj } from '@storybook/react-vite';
import { Tooltip } from '.';

const meta: Meta = {
  title: 'Primitives/Tooltip',
  parameters: { layout: 'centered' },
};

export default meta;
type Story = StoryObj;

export const Default: Story = {
  render: () => (
    <Tooltip.Root>
      <Tooltip.Trigger render={<Button variant="ghost">Hover me</Button>} />
      <Tooltip.Content>Tooltip text</Tooltip.Content>
    </Tooltip.Root>
  ),
};

export const Placements: Story = {
  render: () => (
    <Box display="flex" gap="4">
      {(['top', 'bottom', 'left', 'right'] as const).map((side) => (
        <Tooltip.Root key={side}>
          <Tooltip.Trigger
            render={
              <Button variant="ghost" size="xs">
                {side}
              </Button>
            }
          />
          <Tooltip.Content side={side}>Placed on {side}</Tooltip.Content>
        </Tooltip.Root>
      ))}
    </Box>
  ),
};

export const Aligned: Story = {
  render: () => (
    <Box display="flex" gap="4">
      {(['start', 'center', 'end'] as const).map((align) => (
        <Tooltip.Root key={align}>
          <Tooltip.Trigger
            render={
              <Button variant="ghost" size="xs">
                {align}
              </Button>
            }
          />
          <Tooltip.Content side="bottom" align={align}>
            Aligned: {align}
          </Tooltip.Content>
        </Tooltip.Root>
      ))}
    </Box>
  ),
};

export const WithoutArrow: Story = {
  render: () => (
    <Tooltip.Root>
      <Tooltip.Trigger render={<Button variant="ghost">No arrow</Button>} />
      <Tooltip.Content showArrow={false}>Arrowless tooltip</Tooltip.Content>
    </Tooltip.Root>
  ),
};

export const WithShortcut: Story = {
  render: () => (
    <Tooltip.Root>
      <Tooltip.Trigger render={<Button variant="ghost">Save</Button>} />
      <Tooltip.Content>
        Save file
        <KbdGroup>
          <Kbd>⌘</Kbd>
          <Kbd>S</Kbd>
        </KbdGroup>
      </Tooltip.Content>
    </Tooltip.Root>
  ),
};

export const WithProviderDelay: Story = {
  render: () => (
    <Tooltip.Provider delay={600}>
      <Box display="flex" gap="4">
        {['One', 'Two', 'Three'].map((label) => (
          <Tooltip.Root key={label}>
            <Tooltip.Trigger
              render={
                <Button variant="ghost" size="xs">
                  {label}
                </Button>
              }
            />
            <Tooltip.Content>Tooltip {label}: opens after 600ms, then instantly</Tooltip.Content>
          </Tooltip.Root>
        ))}
      </Box>
    </Tooltip.Provider>
  ),
};

export const LongContent: Story = {
  render: () => (
    <Tooltip.Root>
      <Tooltip.Trigger render={<Button variant="ghost">Long content</Button>} />
      <Tooltip.Content>
        Tooltip content wraps once it reaches the maximum width, which keeps longer explanations
        readable instead of stretching across the screen.
      </Tooltip.Content>
    </Tooltip.Root>
  ),
};
