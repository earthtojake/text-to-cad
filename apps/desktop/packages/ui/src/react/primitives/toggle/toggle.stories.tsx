import { Box } from '@react/primitives/box';
import { Toggle, ToggleGroup } from '@react/primitives/toggle';
import type { Meta, StoryObj } from '@storybook/react-vite';
import { AlignCenterIcon, AlignLeftIcon, AlignRightIcon, BoldIcon, ItalicIcon } from 'lucide-react';
import * as s from '@react/story-layout.css';

const meta: Meta = {
  title: 'Primitives/Toggle',
  parameters: { layout: 'centered' },
};

export default meta;
type Story = StoryObj;

export const Standalone: Story = {
  render: () => (
    <Box display="flex" flexWrap="wrap" alignItems="center" gap="2">
      <Toggle aria-label="Bold">
        <BoldIcon />
      </Toggle>
      <Toggle aria-label="Italic">
        <ItalicIcon />
      </Toggle>
      <Toggle size="xs" aria-label="Bold xs">
        <BoldIcon />
      </Toggle>
    </Box>
  ),
};

export const Group: Story = {
  render: () => (
    <ToggleGroup.Root>
      <ToggleGroup.Item value="left" aria-label="Align left">
        <AlignLeftIcon />
      </ToggleGroup.Item>
      <ToggleGroup.Item value="center" aria-label="Align center">
        <AlignCenterIcon />
      </ToggleGroup.Item>
      <ToggleGroup.Item value="right" aria-label="Align right">
        <AlignRightIcon />
      </ToggleGroup.Item>
    </ToggleGroup.Root>
  ),
};

export const AcrossSurfaces: Story = {
  render: () => (
    <Box
      background="surfaceSunken"
      display="flex"
      flexDirection="column"
      gap="4"
      rounded="xl"
      padding="4"
    >
      {(['sunken', 'base', 'base-emphasis', 'elevated', 'elevated-emphasis'] as const).map(
        (level) => (
          <Box
            key={level}
            surface={level}
            display="flex"
            flexWrap="wrap"
            alignItems="center"
            gap="2"
            rounded="lg"
            padding="3"
          >
            <span
              className={s.w36}
              style={{ fontSize: 'var(--em-text-xs)', color: 'var(--em-foreground-muted)' }}
            >
              {level}
            </span>
            <Toggle pressed aria-label="Bold pressed">
              <BoldIcon />
            </Toggle>
            <Toggle aria-label="Italic">
              <ItalicIcon />
            </Toggle>
            <ToggleGroup.Root>
              <ToggleGroup.Item value="left" aria-label="Left">
                <AlignLeftIcon />
              </ToggleGroup.Item>
              <ToggleGroup.Item value="center" aria-label="Center">
                <AlignCenterIcon />
              </ToggleGroup.Item>
            </ToggleGroup.Root>
          </Box>
        )
      )}
    </Box>
  ),
};
