import type { Meta, StoryObj } from '@storybook/react-vite';
import { useState } from 'react';
import { PromptEditor } from './prompt-editor';

const meta = {
  title: 'Components/PromptEditor',
  component: PromptEditor,
  parameters: { layout: 'centered' },
  decorators: [
    (Story) => (
      <div style={{ width: 560, maxWidth: 'calc(100vw - 32px)', minHeight: 160 }}>
        <Story />
      </div>
    ),
  ],
} satisfies Meta<typeof PromptEditor>;

export default meta;
type Story = StoryObj<typeof meta>;

export const ChatDefaults: Story = {
  args: {
    placeholder: 'Message…',
    onChange: () => {},
    onSubmit: () => {},
  },
};

function ControlledCreateEditor() {
  const [value, setValue] = useState('Review @requirements.md before implementing.');
  return (
    <PromptEditor
      value={value}
      mentions={[
        {
          id: 'requirements',
          label: 'requirements.md',
          name: 'requirements.md',
          kind: 'file',
          pending: true,
          serializedText: '@requirements.md',
        },
      ]}
      placeholder="Describe the Task…"
      submitShortcut="mod-enter"
      clearOnSubmit={false}
      allowEmptySubmit
      onChange={setValue}
      onSubmit={() => {}}
    />
  );
}

export const ControlledCreateMode: Story = {
  args: {},
  render: () => <ControlledCreateEditor />,
};
