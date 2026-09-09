import type { Meta, StoryObj } from '@storybook/react-vite';
import type { ReactNode } from 'react';
import { Resizable } from '.';

const meta: Meta = {
  title: 'Primitives/Resizable',
  parameters: { layout: 'padded' },
};

export default meta;
type Story = StoryObj;

function Frame({ children, height = 320 }: { children: ReactNode; height?: number }) {
  return <div style={{ height, border: '1px solid var(--em-border)' }}>{children}</div>;
}

function PanelContent({ label }: { label: string }) {
  return (
    <div
      style={{
        display: 'flex',
        height: '100%',
        alignItems: 'center',
        justifyContent: 'center',
        fontSize: '0.875rem',
        color: 'var(--em-foreground-muted)',
      }}
    >
      {label}
    </div>
  );
}

export const Horizontal: Story = {
  render: () => (
    <Frame>
      <Resizable.Group orientation="horizontal" id="story-horizontal">
        <Resizable.Panel id="left" defaultSize="30%" minSize="20%">
          <PanelContent label="Left" />
        </Resizable.Panel>
        <Resizable.Handle />
        <Resizable.Panel id="right" minSize="30%">
          <PanelContent label="Right" />
        </Resizable.Panel>
      </Resizable.Group>
    </Frame>
  ),
};

export const Vertical: Story = {
  render: () => (
    <Frame>
      <Resizable.Group orientation="vertical" id="story-vertical">
        <Resizable.Panel id="top" defaultSize="60%" minSize="20%">
          <PanelContent label="Top" />
        </Resizable.Panel>
        <Resizable.Handle />
        <Resizable.Panel id="bottom" minSize="15%">
          <PanelContent label="Bottom" />
        </Resizable.Panel>
      </Resizable.Group>
    </Frame>
  ),
};

/** Mirrors the app's task view: a sidebar split containing a stacked main area. */
export const Nested: Story = {
  render: () => (
    <Frame height={400}>
      <Resizable.Group orientation="horizontal" id="story-nested">
        <Resizable.Panel id="main" minSize="30%">
          <Resizable.Group orientation="vertical" id="story-nested-inner">
            <Resizable.Panel id="content" minSize="30%">
              <PanelContent label="Main content" />
            </Resizable.Panel>
            <Resizable.Handle />
            <Resizable.Panel id="drawer" defaultSize="25%" minSize="15%">
              <PanelContent label="Bottom drawer" />
            </Resizable.Panel>
          </Resizable.Group>
        </Resizable.Panel>
        <Resizable.Handle />
        <Resizable.Panel id="sidebar" defaultSize="25%" minSize="15%" maxSize="50%">
          <PanelContent label="Sidebar" />
        </Resizable.Panel>
      </Resizable.Group>
    </Frame>
  ),
};

/** The `ghost` handle is invisible until hovered — for layouts drawing their own divider. */
export const GhostHandle: Story = {
  render: () => (
    <Frame>
      <Resizable.Group orientation="horizontal" id="story-ghost">
        <Resizable.Panel id="left" defaultSize="30%" minSize="15%">
          <PanelContent label="Hover the gap between the panels" />
        </Resizable.Panel>
        <Resizable.Handle variant="ghost" />
        <Resizable.Panel id="right" minSize="30%">
          <PanelContent label="Right" />
        </Resizable.Panel>
      </Resizable.Group>
    </Frame>
  ),
};

/** Dragging the left panel below its minimum snaps it collapsed. */
export const Collapsible: Story = {
  render: () => (
    <Frame>
      <Resizable.Group orientation="horizontal" id="story-collapsible">
        <Resizable.Panel
          id="left"
          collapsible
          collapsedSize="0%"
          defaultSize="25%"
          minSize="150px"
          maxSize="40%"
        >
          <PanelContent label="Collapsible" />
        </Resizable.Panel>
        <Resizable.Handle />
        <Resizable.Panel id="right" minSize="30%">
          <PanelContent label="Drag the handle far left to collapse" />
        </Resizable.Panel>
      </Resizable.Group>
    </Frame>
  ),
};
