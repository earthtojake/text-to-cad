import { Box } from '@react/primitives/box';
import { Button } from '@react/primitives/button';
import type { Meta, StoryObj } from '@storybook/react-vite';
import { cx } from '@styles/utilities/cx';
import { Popover } from '.';
import { sx } from '@styles/utilities/sprinkles.css';

const meta: Meta = {
  title: 'Primitives/Popover',
  parameters: { layout: 'centered' },
};

export default meta;
type Story = StoryObj;

export const Default: Story = {
  render: () => (
    <Popover.Root>
      <Popover.Trigger render={<Button variant="ghost">Open popover</Button>} />
      <Popover.Content>
        <Popover.Header>
          <Popover.Title>Popover title</Popover.Title>
          <Popover.Description>
            This is a short description of the popover content.
          </Popover.Description>
        </Popover.Header>
        <p className={cx(sx({ fontSize: 'sm', color: 'foregroundMuted' }))}>
          Some body content here.
        </p>
      </Popover.Content>
    </Popover.Root>
  ),
};

export const WithCloseButton: Story = {
  render: () => (
    <Popover.Root>
      <Popover.Trigger render={<Button variant="ghost">Open popover</Button>} />
      <Popover.Content>
        <Popover.Header>
          <Popover.Title>Settings</Popover.Title>
          <Popover.Close
            render={
              <Button variant="ghost" size="xs" icon>
                ×
              </Button>
            }
          />
        </Popover.Header>
        <p className={cx(sx({ fontSize: 'sm', color: 'foregroundMuted' }))}>
          Configure your preferences here.
        </p>
      </Popover.Content>
    </Popover.Root>
  ),
};

export const Aligned: Story = {
  render: () => (
    <Box display="flex" gap="4">
      {(['start', 'center', 'end'] as const).map((align) => (
        <Popover.Root key={align}>
          <Popover.Trigger
            render={
              <Button variant="ghost" size="xs">
                {align}
              </Button>
            }
          />
          <Popover.Content align={align}>
            <p className={cx(sx({ fontSize: 'sm' }))}>Aligned: {align}</p>
          </Popover.Content>
        </Popover.Root>
      ))}
    </Box>
  ),
};
