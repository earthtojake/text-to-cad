import { Box } from '@react/primitives/box';
import { Button } from '@react/primitives/button';
import type { Meta, StoryObj } from '@storybook/react-vite';
import { RocketIcon } from 'lucide-react';
import { useState } from 'react';
import { Alert } from '.';
import * as s from '@react/story-layout.css';

const meta: Meta = {
  title: 'Primitives/Alert',
  parameters: { layout: 'centered' },
};

export default meta;
type Story = StoryObj;

export const Statuses: Story = {
  render: () => (
    <Box display="flex" flexDirection="column" gap="3" className={s.w80}>
      <Alert.Root status="info">
        <Alert.Title>New version available</Alert.Title>
        <Alert.Description>Restart the app to apply Emdash 1.4.0.</Alert.Description>
      </Alert.Root>

      <Alert.Root status="success">
        <Alert.Title>Changes saved</Alert.Title>
        <Alert.Description>Your settings have been updated successfully.</Alert.Description>
      </Alert.Root>

      <Alert.Root status="warning">
        <Alert.Title>SSH key expires soon</Alert.Title>
        <Alert.Description>
          Your key will expire in 3 days. Rotate it to avoid connection failures.
        </Alert.Description>
      </Alert.Root>

      <Alert.Root status="destructive">
        <Alert.Title>Connection failed</Alert.Title>
        <Alert.Description>
          Unable to reach the remote host. Check your SSH config.
        </Alert.Description>
      </Alert.Root>
    </Box>
  ),
};

export const Simple: Story = {
  render: () => (
    <Box display="flex" flexDirection="column" gap="3" className={s.w80}>
      <Alert.Root status="info">Agent is running in the background.</Alert.Root>
      <Alert.Root status="warning">Unsaved changes will be lost.</Alert.Root>
      <Alert.Root status="destructive">Build failed with exit code 1.</Alert.Root>
    </Box>
  ),
};

export const Dismissible: Story = {
  render: function DismissibleAlerts() {
    const [visible, setVisible] = useState({
      info: true,
      success: true,
      warning: true,
      destructive: true,
    });

    return (
      <Box display="flex" flexDirection="column" gap="3" className={s.w80}>
        {visible.info && (
          <Alert.Root status="info" onDismiss={() => setVisible((v) => ({ ...v, info: false }))}>
            <Alert.Title>Update available</Alert.Title>
            <Alert.Description>Emdash 1.5.0 is ready to install.</Alert.Description>
          </Alert.Root>
        )}
        {visible.success && (
          <Alert.Root
            status="success"
            onDismiss={() => setVisible((v) => ({ ...v, success: false }))}
          >
            <Alert.Title>Deployment complete</Alert.Title>
            <Alert.Description>Your app is live at production.</Alert.Description>
          </Alert.Root>
        )}
        {visible.warning && (
          <Alert.Root
            status="warning"
            onDismiss={() => setVisible((v) => ({ ...v, warning: false }))}
          >
            <Alert.Title>Rate limit approaching</Alert.Title>
            <Alert.Description>80% of your API quota used this month.</Alert.Description>
          </Alert.Root>
        )}
        {visible.destructive && (
          <Alert.Root
            status="destructive"
            onDismiss={() => setVisible((v) => ({ ...v, destructive: false }))}
          >
            <Alert.Title>Task failed</Alert.Title>
            <Alert.Description>The agent exited with an unhandled error.</Alert.Description>
          </Alert.Root>
        )}
        {Object.values(visible).every((v) => !v) && (
          <Box display="flex" flexDirection="column" gap="2" style={{ alignItems: 'center' }}>
            <span style={{ fontSize: 'var(--em-text-sm)', color: 'var(--em-foreground-muted)' }}>
              All alerts dismissed.
            </span>
            <Button
              variant="ghost"
              onClick={() =>
                setVisible({ info: true, success: true, warning: true, destructive: true })
              }
            >
              Reset
            </Button>
          </Box>
        )}
      </Box>
    );
  },
};

/** Action slot — a free-form control pinned to the top-right corner. */
export const WithAction: Story = {
  render: () => (
    <Box display="flex" flexDirection="column" gap="3" className={s.w80}>
      <Alert.Root status="warning">
        <Alert.Title>CLI not found</Alert.Title>
        <Alert.Description>The claude binary is missing from your PATH.</Alert.Description>
        <Alert.Action>
          <Button variant="secondary" size="xs">
            Install
          </Button>
        </Alert.Action>
      </Alert.Root>
      <Alert.Root status="destructive">
        <Alert.Title>Sync failed</Alert.Title>
        <Alert.Description>The remote rejected the push.</Alert.Description>
        <Alert.Action>
          <Button variant="secondary" size="xs">
            Retry
          </Button>
        </Alert.Action>
      </Alert.Root>
    </Box>
  ),
};

export const NoIcon: Story = {
  render: () => (
    <Box display="flex" flexDirection="column" gap="3" className={s.w80}>
      <Alert.Root status="info" icon={null}>
        <Alert.Title>Heads up</Alert.Title>
        <Alert.Description>This section requires admin access.</Alert.Description>
      </Alert.Root>
      <Alert.Root status="destructive" icon={null}>
        Build failed — check the logs below.
      </Alert.Root>
    </Box>
  ),
};

export const CustomIcon: Story = {
  render: () => (
    <Alert.Root status="success" icon={<RocketIcon />} className={s.w80}>
      <Alert.Title>Agent launched</Alert.Title>
      <Alert.Description>Claude is now running on your branch.</Alert.Description>
    </Alert.Root>
  ),
};
