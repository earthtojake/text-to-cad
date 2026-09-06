import { Box } from '@react/primitives/box';
import type { Meta, StoryObj } from '@storybook/react-vite';
import { SearchIcon, XIcon } from 'lucide-react';
import { InputGroup } from '.';
import * as s from '@react/story-layout.css';

const meta: Meta = {
  title: 'Primitives/InputGroup',
  parameters: { layout: 'centered' },
};

export default meta;
type Story = StoryObj;

export const WithLeadingIcon: Story = {
  render: () => (
    <Box className={s.w72}>
      <InputGroup.Root>
        <InputGroup.Addon align="inline-start">
          <SearchIcon />
        </InputGroup.Addon>
        <InputGroup.Input placeholder="Search…" />
      </InputGroup.Root>
    </Box>
  ),
};

export const WithTrailingButton: Story = {
  render: () => (
    <Box className={s.w72}>
      <InputGroup.Root>
        <InputGroup.Input placeholder="Search…" />
        <InputGroup.Addon align="inline-end">
          <InputGroup.Button>
            <XIcon />
          </InputGroup.Button>
        </InputGroup.Addon>
      </InputGroup.Root>
    </Box>
  ),
};

export const WithPrefixText: Story = {
  render: () => (
    <Box className={s.w72}>
      <InputGroup.Root>
        <InputGroup.Addon align="inline-start">
          <InputGroup.Text>https://</InputGroup.Text>
        </InputGroup.Addon>
        <InputGroup.Input placeholder="example.com" />
      </InputGroup.Root>
    </Box>
  ),
};

export const WithTextarea: Story = {
  render: () => (
    <Box className={s.w72}>
      <InputGroup.Root>
        <InputGroup.Addon align="block-start">
          <InputGroup.Text>Note</InputGroup.Text>
        </InputGroup.Addon>
        <InputGroup.Textarea placeholder="Write something…" rows={3} />
      </InputGroup.Root>
    </Box>
  ),
};

export const Invalid: Story = {
  render: () => (
    <Box className={s.w72}>
      <InputGroup.Root>
        <InputGroup.Addon align="inline-start">
          <SearchIcon />
        </InputGroup.Addon>
        <InputGroup.Input placeholder="Search…" aria-invalid="true" />
      </InputGroup.Root>
    </Box>
  ),
};
