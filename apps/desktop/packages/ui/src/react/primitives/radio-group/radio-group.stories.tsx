import { RadioGroup } from '@react/primitives/radio-group';
import type { Meta, StoryObj } from '@storybook/react-vite';
import { useState } from 'react';

const meta: Meta = {
  title: 'Primitives/RadioGroup',
  parameters: { layout: 'centered' },
};

export default meta;
type Story = StoryObj;

const options = [
  { value: 'password', label: 'Password' },
  { value: 'key', label: 'SSH Key' },
  { value: 'agent', label: 'Agent' },
];

function RadioOptions({ disabled = false }: { disabled?: boolean }) {
  return options.map((option) => (
    <label
      key={option.value}
      style={{ display: 'flex', cursor: disabled ? 'not-allowed' : 'pointer', gap: '0.5rem' }}
    >
      <RadioGroup.Item value={option.value} disabled={disabled} />
      {option.label}
    </label>
  ));
}

export const Default: Story = {
  render: () => (
    <RadioGroup.Root defaultValue="password" aria-label="Authentication method">
      <RadioOptions />
    </RadioGroup.Root>
  ),
};

export const Controlled: Story = {
  render: function ControlledRadioGroup() {
    const [value, setValue] = useState('password');

    return (
      <div style={{ display: 'grid', gap: '0.75rem' }}>
        <RadioGroup.Root value={value} onValueChange={setValue} aria-label="Authentication method">
          <RadioOptions />
        </RadioGroup.Root>
        <span style={{ fontSize: 'var(--em-text-sm)' }}>Selected: {value}</span>
      </div>
    );
  },
};

export const Disabled: Story = {
  render: () => (
    <RadioGroup.Root defaultValue="key" aria-label="Disabled authentication method">
      <RadioOptions disabled />
    </RadioGroup.Root>
  ),
};
