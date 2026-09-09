import { Button } from '@react/primitives/button';
import type { Meta, StoryObj } from '@storybook/react-vite';
import { BoldIcon, CopyIcon, ItalicIcon, ScissorsIcon, UnderlineIcon } from 'lucide-react';
import { useState } from 'react';
import { DropdownMenu } from '.';

const meta: Meta = {
  title: 'Primitives/DropdownMenu',
  parameters: { layout: 'centered' },
};

export default meta;
type Story = StoryObj;

export const Default: Story = {
  render: () => (
    <DropdownMenu.Root>
      <DropdownMenu.Trigger render={<Button variant="ghost">Open menu</Button>} />
      <DropdownMenu.Content>
        <DropdownMenu.Group>
          <DropdownMenu.Item>
            <CopyIcon />
            Copy
            <DropdownMenu.Shortcut>⌘C</DropdownMenu.Shortcut>
          </DropdownMenu.Item>
          <DropdownMenu.Item>
            <ScissorsIcon />
            Cut
            <DropdownMenu.Shortcut>⌘X</DropdownMenu.Shortcut>
          </DropdownMenu.Item>
        </DropdownMenu.Group>
        <DropdownMenu.Separator />
        <DropdownMenu.Item variant="destructive">Delete</DropdownMenu.Item>
      </DropdownMenu.Content>
    </DropdownMenu.Root>
  ),
};

export const WithLabel: Story = {
  render: () => (
    <DropdownMenu.Root>
      <DropdownMenu.Trigger render={<Button variant="ghost">Open menu</Button>} />
      <DropdownMenu.Content>
        <DropdownMenu.Group>
          <DropdownMenu.Label>Text formatting</DropdownMenu.Label>
          <DropdownMenu.Separator />
          <DropdownMenu.Item>
            <BoldIcon />
            Bold
            <DropdownMenu.Shortcut>⌘B</DropdownMenu.Shortcut>
          </DropdownMenu.Item>
          <DropdownMenu.Item>
            <ItalicIcon />
            Italic
            <DropdownMenu.Shortcut>⌘I</DropdownMenu.Shortcut>
          </DropdownMenu.Item>
          <DropdownMenu.Item>
            <UnderlineIcon />
            Underline
            <DropdownMenu.Shortcut>⌘U</DropdownMenu.Shortcut>
          </DropdownMenu.Item>
        </DropdownMenu.Group>
      </DropdownMenu.Content>
    </DropdownMenu.Root>
  ),
};

export const WithCheckboxItems: Story = {
  render: function Render() {
    const [bold, setBold] = useState(true);
    const [italic, setItalic] = useState(false);
    return (
      <DropdownMenu.Root>
        <DropdownMenu.Trigger render={<Button variant="ghost">Text options</Button>} />
        <DropdownMenu.Content>
          <DropdownMenu.Group>
            <DropdownMenu.CheckboxItem checked={bold} onCheckedChange={setBold}>
              Bold
            </DropdownMenu.CheckboxItem>
            <DropdownMenu.CheckboxItem checked={italic} onCheckedChange={setItalic}>
              Italic
            </DropdownMenu.CheckboxItem>
          </DropdownMenu.Group>
        </DropdownMenu.Content>
      </DropdownMenu.Root>
    );
  },
};

export const WithRadioItems: Story = {
  render: function Render() {
    const [position, setPosition] = useState('center');
    return (
      <DropdownMenu.Root>
        <DropdownMenu.Trigger render={<Button variant="ghost">Alignment: {position}</Button>} />
        <DropdownMenu.Content>
          <DropdownMenu.RadioGroup value={position} onValueChange={setPosition}>
            <DropdownMenu.RadioItem value="left">Left</DropdownMenu.RadioItem>
            <DropdownMenu.RadioItem value="center">Center</DropdownMenu.RadioItem>
            <DropdownMenu.RadioItem value="right">Right</DropdownMenu.RadioItem>
          </DropdownMenu.RadioGroup>
        </DropdownMenu.Content>
      </DropdownMenu.Root>
    );
  },
};

export const WithSubMenu: Story = {
  render: () => (
    <DropdownMenu.Root>
      <DropdownMenu.Trigger render={<Button variant="ghost">Open menu</Button>} />
      <DropdownMenu.Content>
        <DropdownMenu.Item>Profile</DropdownMenu.Item>
        <DropdownMenu.Sub>
          <DropdownMenu.SubTrigger>More options</DropdownMenu.SubTrigger>
          <DropdownMenu.SubContent>
            <DropdownMenu.Item>Settings</DropdownMenu.Item>
            <DropdownMenu.Item>Help</DropdownMenu.Item>
          </DropdownMenu.SubContent>
        </DropdownMenu.Sub>
        <DropdownMenu.Separator />
        <DropdownMenu.Item variant="destructive">Log out</DropdownMenu.Item>
      </DropdownMenu.Content>
    </DropdownMenu.Root>
  ),
};

export const TriggerWidth: Story = {
  render: () => (
    <DropdownMenu.Root>
      <DropdownMenu.Trigger render={<Button variant="ghost">Wide trigger menu</Button>} />
      <DropdownMenu.Content width="trigger">
        <DropdownMenu.Item>Matches trigger width</DropdownMenu.Item>
        <DropdownMenu.Item>Second action</DropdownMenu.Item>
      </DropdownMenu.Content>
    </DropdownMenu.Root>
  ),
};
