import type { Meta, StoryObj } from '@storybook/react-vite';
import {
  Activity,
  Brain,
  Folder,
  GitPullRequest,
  ListTodo,
  MessageSquare,
  PanelsTopLeft,
  Server,
  Settings,
  User,
} from 'lucide-react';
import { useState } from 'react';
import { PillTabs, type PillTab, type PillTabsLabelVisibility } from './pill-tabs';

const meta: Meta = {
  title: 'Patterns/PillTabs',
  parameters: { layout: 'padded' },
};

export default meta;
type Story = StoryObj;

type ProjectSection = 'tasks' | 'pull-requests' | 'workspaces' | 'settings';

const projectTabs: readonly PillTab<ProjectSection>[] = [
  { value: 'tasks', label: 'Tasks', icon: <ListTodo /> },
  { value: 'pull-requests', label: 'Pull Requests', icon: <GitPullRequest /> },
  { value: 'workspaces', label: 'Workspaces', icon: <PanelsTopLeft /> },
  { value: 'settings', label: 'Settings', icon: <Settings /> },
];

function ProjectTabsExample({
  labelVisibility = 'always',
  disabled,
}: {
  labelVisibility?: PillTabsLabelVisibility;
  disabled?: ProjectSection;
}) {
  const [value, setValue] = useState<ProjectSection>('tasks');
  const items = projectTabs.map((item) => ({
    ...item,
    disabled: item.value === disabled,
  }));
  return (
    <PillTabs
      items={items}
      value={value}
      onValueChange={setValue}
      ariaLabel="Project sections"
      labelVisibility={labelVisibility}
    />
  );
}

export const AlwaysVisibleLabels: Story = {
  render: () => <ProjectTabsExample />,
};

export const ActiveLabelOnly: Story = {
  render: () => <ProjectTabsExample labelVisibility="active-only" />,
};

export const DisabledTab: Story = {
  render: () => <ProjectTabsExample labelVisibility="active-only" disabled="pull-requests" />,
};

export const NarrowWidth: Story = {
  render: () => (
    <div style={{ width: '20rem' }}>
      <ProjectTabsExample labelVisibility="active-only" />
    </div>
  ),
};

type MachineSection = 'system' | 'workspaces' | 'conversations' | 'agents' | 'mcp' | 'skills';

const machineTabs: readonly PillTab<MachineSection>[] = [
  { value: 'system', label: 'System', icon: <Activity /> },
  { value: 'workspaces', label: 'Workspaces', icon: <Folder /> },
  { value: 'conversations', label: 'Conversations', icon: <MessageSquare /> },
  { value: 'agents', label: 'Agents', icon: <User /> },
  { value: 'mcp', label: 'MCP', icon: <Server /> },
  { value: 'skills', label: 'Skills', icon: <Brain /> },
];

function MachineTabsExample() {
  const [value, setValue] = useState<MachineSection>('system');
  return (
    <PillTabs
      items={machineTabs}
      value={value}
      onValueChange={setValue}
      ariaLabel="Machine sections"
      labelVisibility="active-only"
    />
  );
}

export const SixTabs: Story = {
  render: () => <MachineTabsExample />,
};
