import { Box } from '@react/primitives/box';
import type { Meta, StoryObj } from '@storybook/react-vite';
import { useState } from 'react';
import { SeparatedList } from '@/react/primitives/separated-list';
import { Collapsible } from '.';
import * as s from '@react/story-layout.css';

const meta: Meta = {
  title: 'Primitives/Collapsible',
  parameters: { layout: 'centered' },
};

export default meta;
type Story = StoryObj;

export const Default: Story = {
  render: () => (
    <Collapsible.Root className={s.w72}>
      <Collapsible.Trigger>Advanced settings</Collapsible.Trigger>
      <Collapsible.Panel>
        <Box display="flex" flexDirection="column" gap="2" style={{ paddingTop: '0.5rem' }}>
          <span style={{ fontSize: 'var(--em-text-sm)', color: 'var(--em-foreground-muted)' }}>
            These settings are hidden by default.
          </span>
          <span style={{ fontSize: 'var(--em-text-sm)' }}>Setting A: enabled</span>
          <span style={{ fontSize: 'var(--em-text-sm)' }}>Setting B: disabled</span>
        </Box>
      </Collapsible.Panel>
    </Collapsible.Root>
  ),
};

export const DefaultOpen: Story = {
  render: () => (
    <Collapsible.Root defaultOpen className={s.w72}>
      <Collapsible.Trigger>Session details</Collapsible.Trigger>
      <Collapsible.Panel>
        <Box display="flex" flexDirection="column" gap="2" style={{ paddingTop: '0.5rem' }}>
          <span style={{ fontSize: 'var(--em-text-sm)' }}>Branch: feature/my-feature</span>
          <span style={{ fontSize: 'var(--em-text-sm)' }}>Worktree: /tmp/my-feature</span>
          <span style={{ fontSize: 'var(--em-text-sm)' }}>Agent: Claude</span>
        </Box>
      </Collapsible.Panel>
    </Collapsible.Root>
  ),
};

export const Controlled: Story = {
  render: function ControlledCollapsible() {
    const [open, setOpen] = useState(false);
    return (
      <Box display="flex" flexDirection="column" gap="3" className={s.w72}>
        <span
          style={{
            fontSize: 'var(--em-text-xs)',
            color: 'var(--em-foreground-muted)',
          }}
        >
          Panel is {open ? 'open' : 'closed'}
        </span>
        <Collapsible.Root open={open} onOpenChange={setOpen}>
          <Collapsible.Trigger>Toggle panel</Collapsible.Trigger>
          <Collapsible.Panel>
            <Box style={{ paddingTop: '0.5rem' }}>
              <span style={{ fontSize: 'var(--em-text-sm)' }}>Controlled content revealed.</span>
            </Box>
          </Collapsible.Panel>
        </Collapsible.Root>
      </Box>
    );
  },
};

export const Disabled: Story = {
  render: () => (
    <Collapsible.Root disabled className={s.w72}>
      <Collapsible.Trigger>Locked section</Collapsible.Trigger>
      <Collapsible.Panel>
        <span style={{ fontSize: 'var(--em-text-sm)' }}>Never shown.</span>
      </Collapsible.Panel>
    </Collapsible.Root>
  ),
};

export const SettingsGroup: Story = {
  render: () => (
    <Box display="flex" flexDirection="column" gap="0" className={s.w80}>
      <Collapsible.Root defaultOpen>
        <Collapsible.Trigger>General</Collapsible.Trigger>
        <Collapsible.Panel>
          <SeparatedList
            gap="0.5rem"
            style={{ paddingTop: '0.25rem', paddingBottom: '0.25rem', paddingLeft: '0.5rem' }}
          >
            <span style={{ fontSize: 'var(--em-text-sm)' }}>Display name</span>
            <span style={{ fontSize: 'var(--em-text-sm)' }}>Theme</span>
            <span style={{ fontSize: 'var(--em-text-sm)' }}>Language</span>
          </SeparatedList>
        </Collapsible.Panel>
      </Collapsible.Root>
      <Collapsible.Root>
        <Collapsible.Trigger>SSH &amp; Connections</Collapsible.Trigger>
        <Collapsible.Panel>
          <SeparatedList
            gap="0.5rem"
            style={{ paddingTop: '0.25rem', paddingBottom: '0.25rem', paddingLeft: '0.5rem' }}
          >
            <span style={{ fontSize: 'var(--em-text-sm)' }}>Default SSH key</span>
            <span style={{ fontSize: 'var(--em-text-sm)' }}>Timeout</span>
          </SeparatedList>
        </Collapsible.Panel>
      </Collapsible.Root>
      <Collapsible.Root>
        <Collapsible.Trigger>Telemetry</Collapsible.Trigger>
        <Collapsible.Panel>
          <Box style={{ padding: '0.5rem' }}>
            <span style={{ fontSize: 'var(--em-text-sm)', color: 'var(--em-foreground-muted)' }}>
              No telemetry settings configured.
            </span>
          </Box>
        </Collapsible.Panel>
      </Collapsible.Root>
    </Box>
  ),
};
