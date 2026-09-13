import { Box } from '@react/primitives/box';
import type { Meta, StoryObj } from '@storybook/react-vite';
import { TriggerButton } from '.';
import { DropdownMenu } from '../dropdown-menu';
import { Select } from '../select';
import * as s from '@react/story-layout.css';

const meta: Meta = {
  title: 'Primitives/TriggerButton',
  parameters: { layout: 'centered' },
};

export default meta;
type Story = StoryObj;

export const Bare: Story = {
  render: () => (
    <Box display="flex" flexWrap="wrap" alignItems="center" gap="3">
      <TriggerButton>Choose an option</TriggerButton>
      <TriggerButton size="xs">Small trigger</TriggerButton>
      <TriggerButton showChevron={false}>No chevron</TriggerButton>
    </Box>
  ),
};

export const AsSelectTrigger: Story = {
  render: () => (
    <Select.Root>
      <Select.Trigger className={s.w48}>
        <Select.Value placeholder="Pick an option" />
      </Select.Trigger>
      <Select.Content>
        <Select.Item value="a">Alpha</Select.Item>
        <Select.Item value="b">Beta</Select.Item>
        <Select.Item value="c">Gamma</Select.Item>
      </Select.Content>
    </Select.Root>
  ),
};

export const AsDropdownTrigger: Story = {
  render: () => (
    <DropdownMenu.Root>
      <DropdownMenu.Trigger render={<TriggerButton className={s.w48}>Actions</TriggerButton>} />
      <DropdownMenu.Content>
        <DropdownMenu.Item>Edit</DropdownMenu.Item>
        <DropdownMenu.Item>Duplicate</DropdownMenu.Item>
        <DropdownMenu.Item variant="destructive">Delete</DropdownMenu.Item>
      </DropdownMenu.Content>
    </DropdownMenu.Root>
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
            <Select.Root>
              <Select.Trigger className={s.w40}>
                <Select.Value placeholder="Select…" />
              </Select.Trigger>
              <Select.Content>
                <Select.Item value="a">Alpha</Select.Item>
                <Select.Item value="b">Beta</Select.Item>
              </Select.Content>
            </Select.Root>
          </Box>
        )
      )}
    </Box>
  ),
};
