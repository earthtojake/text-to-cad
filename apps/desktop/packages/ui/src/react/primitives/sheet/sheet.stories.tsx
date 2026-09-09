import { Box } from '@react/primitives/box';
import { Button } from '@react/primitives/button';
import { Sheet } from '@react/primitives/sheet';
import type { Meta, StoryObj } from '@storybook/react-vite';
import { cx } from '@styles/utilities/cx';
import { sx } from '@styles/utilities/sprinkles.css';

const meta: Meta = {
  title: 'Primitives/Sheet',
  parameters: { layout: 'centered' },
};
export default meta;

type Story = StoryObj;

export const Default: Story = {
  render: () => (
    <Sheet.Root>
      <Sheet.Trigger render={<Button variant="ghost">Open sheet</Button>} />
      <Sheet.Content>
        <Sheet.Header>
          <Sheet.Title>Sheet title</Sheet.Title>
        </Sheet.Header>
        <Sheet.Body>
          <p className={cx(sx({ color: 'foregroundMuted' }))}>
            This is the sheet body. Place forms, content, or any composition here. The body scrolls
            independently when it overflows, with a top fade when scrolled down.
          </p>
        </Sheet.Body>
        <Sheet.Footer>
          <Sheet.Close render={<Button variant="ghost">Cancel</Button>} />
          <Sheet.Close render={<Button variant="primary">Save</Button>} />
        </Sheet.Footer>
      </Sheet.Content>
    </Sheet.Root>
  ),
};

export const LeftSide: Story = {
  render: () => (
    <Sheet.Root>
      <Sheet.Trigger render={<Button variant="ghost">Open left sheet</Button>} />
      <Sheet.Content side="left">
        <Sheet.Header>
          <Sheet.Title>Navigation</Sheet.Title>
        </Sheet.Header>
        <Sheet.Body>
          <p className={cx(sx({ color: 'foregroundMuted' }))}>
            This sheet slides in from the left. Use it for navigation drawers, sidebars, or
            secondary panels.
          </p>
          <Box marginTop="4" display="flex" flexDirection="column" gap="1">
            {['Overview', 'Tasks', 'Settings', 'Members', 'Integrations'].map((item) => (
              <button
                key={item}
                type="button"
                className={cx(
                  sx({
                    background: 'surfaceBaseEmphasis',
                    rounded: 'lg',
                    px: '3',
                    py: '2',
                    textAlign: 'left',
                    fontSize: 'sm',
                    color: 'foreground',
                  })
                )}
              >
                {item}
              </button>
            ))}
          </Box>
        </Sheet.Body>
        <Sheet.Footer>
          <Sheet.Close render={<Button variant="ghost">Close</Button>} />
        </Sheet.Footer>
      </Sheet.Content>
    </Sheet.Root>
  ),
};

export const TopSide: Story = {
  render: () => (
    <Sheet.Root>
      <Sheet.Trigger render={<Button variant="ghost">Open top sheet</Button>} />
      <Sheet.Content side="top">
        <Sheet.Header>
          <Sheet.Title>Announcement</Sheet.Title>
        </Sheet.Header>
        <Sheet.Body>
          <p className={cx(sx({ color: 'foregroundMuted' }))}>
            This sheet slides in from the top and spans the full width. It sizes to its content up
            to 75% of the viewport height.
          </p>
        </Sheet.Body>
      </Sheet.Content>
    </Sheet.Root>
  ),
};

export const BottomSide: Story = {
  render: () => (
    <Sheet.Root>
      <Sheet.Trigger render={<Button variant="ghost">Open bottom sheet</Button>} />
      <Sheet.Content side="bottom">
        <Sheet.Header>
          <Sheet.Title>Quick actions</Sheet.Title>
        </Sheet.Header>
        <Sheet.Body>
          <p className={cx(sx({ color: 'foregroundMuted' }))}>
            This sheet slides in from the bottom and spans the full width. Use it for action trays
            or transient panels anchored to the bottom edge.
          </p>
        </Sheet.Body>
        <Sheet.Footer>
          <Sheet.Close render={<Button variant="ghost">Dismiss</Button>} />
        </Sheet.Footer>
      </Sheet.Content>
    </Sheet.Root>
  ),
};

export const ScrollableBody: Story = {
  render: () => (
    <Sheet.Root>
      <Sheet.Trigger render={<Button variant="ghost">Open scrollable sheet</Button>} />
      <Sheet.Content>
        <Sheet.Header>
          <Sheet.Title>Changelog</Sheet.Title>
        </Sheet.Header>
        <Sheet.Body>
          {Array.from({ length: 20 }, (_, i) => (
            <p key={i} className={cx(sx({ color: 'foregroundMuted' }))}>
              {i + 1}. Lorem ipsum dolor sit amet, consectetur adipiscing elit. Sed do eiusmod
              tempor incididunt ut labore et dolore magna aliqua.
            </p>
          ))}
        </Sheet.Body>
        <Sheet.Footer>
          <Sheet.Close render={<Button variant="ghost">Dismiss</Button>} />
        </Sheet.Footer>
      </Sheet.Content>
    </Sheet.Root>
  ),
};

export const WithoutFooter: Story = {
  render: () => (
    <Sheet.Root>
      <Sheet.Trigger render={<Button variant="ghost">Open detail sheet</Button>} />
      <Sheet.Content>
        <Sheet.Header>
          <Sheet.Title>Details</Sheet.Title>
        </Sheet.Header>
        <Sheet.Body>
          <p className={cx(sx({ color: 'foregroundMuted' }))}>
            This sheet has no footer — the close button in the header is the only dismiss
            affordance. Useful for detail panels, previews, or read-only views.
          </p>
          <Box
            marginTop="4"
            rounded="lg"
            borderWidth="1"
            borderStyle="solid"
            borderColor="border"
            padding="3"
            fontSize="xs"
            style={{ color: 'var(--em-foreground-muted)' }}
          >
            <p className={cx(sx({ color: 'foreground' }))}>Component</p>
            <p>packages/ui/src/primitives/sheet.tsx</p>
          </Box>
        </Sheet.Body>
      </Sheet.Content>
    </Sheet.Root>
  ),
};
