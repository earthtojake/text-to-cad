import type { Meta, StoryObj } from '@storybook/react-vite';
import { Select } from '.';
import { Box } from '../box';
import * as s from '@react/story-layout.css';

const meta: Meta = {
  title: 'Primitives/Select',
  parameters: { layout: 'centered' },
};

export default meta;
type Story = StoryObj;

export const Default: Story = {
  render: () => (
    <Box className={s.w48}>
      <Select.Root>
        <Select.Trigger>
          <Select.Value placeholder="Pick a fruit" />
        </Select.Trigger>
        <Select.Content>
          <Select.Item value="apple">Apple</Select.Item>
          <Select.Item value="banana">Banana</Select.Item>
          <Select.Item value="cherry">Cherry</Select.Item>
        </Select.Content>
      </Select.Root>
    </Box>
  ),
};

export const WithGroups: Story = {
  render: () => (
    <Box className={s.w48}>
      <Select.Root>
        <Select.Trigger>
          <Select.Value placeholder="Pick a food" />
        </Select.Trigger>
        <Select.Content>
          <Select.Group>
            <Select.Label>Fruits</Select.Label>
            <Select.Item value="apple">Apple</Select.Item>
            <Select.Item value="banana">Banana</Select.Item>
          </Select.Group>
          <Select.Separator />
          <Select.Group>
            <Select.Label>Vegetables</Select.Label>
            <Select.Item value="carrot">Carrot</Select.Item>
            <Select.Item value="pea">Pea</Select.Item>
          </Select.Group>
        </Select.Content>
      </Select.Root>
    </Box>
  ),
};

export const WithDefaultValue: Story = {
  render: () => (
    <Box className={s.w48}>
      <Select.Root defaultValue="banana">
        <Select.Trigger>
          <Select.Value />
        </Select.Trigger>
        <Select.Content>
          <Select.Item value="apple">Apple</Select.Item>
          <Select.Item value="banana">Banana</Select.Item>
          <Select.Item value="cherry">Cherry</Select.Item>
        </Select.Content>
      </Select.Root>
    </Box>
  ),
};

export const Disabled: Story = {
  render: () => (
    <Box className={s.w48}>
      <Select.Root disabled>
        <Select.Trigger>
          <Select.Value placeholder="Disabled" />
        </Select.Trigger>
        <Select.Content>
          <Select.Item value="apple">Apple</Select.Item>
        </Select.Content>
      </Select.Root>
    </Box>
  ),
};

export const WithDisabledItem: Story = {
  render: () => (
    <Box className={s.w48}>
      <Select.Root>
        <Select.Trigger>
          <Select.Value placeholder="Pick a fruit" />
        </Select.Trigger>
        <Select.Content>
          <Select.Item value="apple">Apple</Select.Item>
          <Select.Item value="banana" disabled>
            Banana (unavailable)
          </Select.Item>
          <Select.Item value="cherry">Cherry</Select.Item>
        </Select.Content>
      </Select.Root>
    </Box>
  ),
};

export const ContentSizing: Story = {
  render: () => (
    <Box className={s.w48}>
      <Select.Root defaultValue="short">
        <Select.Trigger>
          <Select.Value />
        </Select.Trigger>
        <Select.Content width="content-at-least-trigger">
          <Select.Item value="short">Short</Select.Item>
          <Select.Item value="long">A much longer option that expands the popup</Select.Item>
        </Select.Content>
      </Select.Root>
    </Box>
  ),
};
