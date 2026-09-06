import { Box } from '@react/primitives/box';
import { Button } from '@react/primitives/button';
import { Input } from '@react/primitives/input';
import { Select } from '@react/primitives/select';
import { SeparatedList } from '@react/primitives/separated-list';
import { Switch } from '@react/primitives/switch';
import type { Meta, StoryObj } from '@storybook/react-vite';
import { useState } from 'react';
import { useAppForm } from '../form/use-app-form';
import { PageLayout } from '../page-layout';
import { SettingsCard } from './settings-card';
import { SettingsRow } from './settings-row';
import { SettingsSection } from './settings-section';
import * as s from '@react/story-layout.css';

const meta: Meta<typeof SettingsCard> = {
  title: 'Patterns/Settings',
  component: SettingsCard,
  parameters: { layout: 'centered' },
};

export default meta;
type Story = StoryObj<typeof meta>;

const storyWidth = { width: 'min(42rem, calc(100vw - 6rem))' };

function DefaultSettings() {
  const [automaticUpdates, setAutomaticUpdates] = useState(true);

  return (
    <Box className={s.maxW2xl} style={storyWidth}>
      <SettingsCard>
        <SeparatedList gap="0.75rem" direction="column">
          <SettingsRow
            label="Automatic updates"
            description="Download new versions when they become available."
            htmlFor="automatic-updates"
            control={
              <Switch
                id="automatic-updates"
                checked={automaticUpdates}
                onCheckedChange={setAutomaticUpdates}
              />
            }
          />
          <SettingsRow
            label="Color mode"
            description="Choose how the interface appears."
            htmlFor="color-mode"
            control={
              <Select.Root defaultValue="system">
                <Select.Trigger id="color-mode">
                  <Select.Value />
                </Select.Trigger>
                <Select.Content>
                  <Select.Item value="system">System</Select.Item>
                  <Select.Item value="light">Light</Select.Item>
                  <Select.Item value="dark">Dark</Select.Item>
                </Select.Content>
              </Select.Root>
            }
          />
          <SettingsRow
            label="Application version"
            description="You are using the latest version."
            control={
              <Button variant="secondary" size="xs">
                Check for updates
              </Button>
            }
          />
        </SeparatedList>
      </SettingsCard>
    </Box>
  );
}

export const Default: Story = {
  render: () => <DefaultSettings />,
};

function FormSettings() {
  const form = useAppForm({
    defaultValues: {
      telemetry: true,
      theme: 'system',
      displayName: 'Emdash',
    },
    onSubmit: () => {},
  });

  return (
    <Box className={s.maxW2xl} style={storyWidth}>
      <SettingsCard>
        <form
          onSubmit={(event) => {
            event.preventDefault();
            void form.handleSubmit();
          }}
        >
          <SeparatedList gap="0.75rem" direction="column">
            <form.AppField name="telemetry">
              {(field) => (
                <SettingsRow
                  label="Send telemetry"
                  description="Anonymous usage data helps improve the application."
                  htmlFor="telemetry"
                  control={
                    <Switch
                      id="telemetry"
                      checked={field.state.value ?? false}
                      onCheckedChange={(checked) => field.handleChange(checked)}
                      onBlur={field.handleBlur}
                    />
                  }
                />
              )}
            </form.AppField>

            <form.AppField name="theme">
              {(field) => (
                <SettingsRow
                  label="Theme"
                  description="Appearance of the interface."
                  htmlFor="theme"
                  control={
                    <Select.Root
                      value={field.state.value}
                      onValueChange={(value) => {
                        if (value !== null) field.handleChange(value);
                      }}
                    >
                      <Select.Trigger id="theme">
                        <Select.Value />
                      </Select.Trigger>
                      <Select.Content>
                        <Select.Item value="system">System</Select.Item>
                        <Select.Item value="light">Light</Select.Item>
                        <Select.Item value="dark">Dark</Select.Item>
                      </Select.Content>
                    </Select.Root>
                  }
                />
              )}
            </form.AppField>

            <form.AppField name="displayName">
              {(field) => (
                <SettingsRow
                  label="Display name"
                  description="Shown in shared application surfaces."
                  htmlFor="display-name"
                  control={
                    <Input
                      id="display-name"
                      name={field.name}
                      value={field.state.value ?? ''}
                      onChange={(event) => field.handleChange(event.target.value)}
                      onBlur={field.handleBlur}
                      className={s.w40}
                    />
                  }
                />
              )}
            </form.AppField>
          </SeparatedList>
        </form>
      </SettingsCard>
    </Box>
  );
}

export const WithFormFields: Story = {
  render: () => <FormSettings />,
};

function PageAnatomy() {
  const [autoUpdate, setAutoUpdate] = useState(true);
  const [telemetry, setTelemetry] = useState(false);

  return (
    <div style={{ height: '100vh', overflowY: 'auto' }}>
      <div style={{ ...storyWidth, margin: '0 auto', paddingBottom: '4rem' }}>
        <PageLayout.Header
          sticky
          title="Interface"
          description="Customize the appearance and behavior of the app."
        />
        <div style={{ display: 'flex', flexDirection: 'column', gap: '2rem', marginTop: '2rem' }}>
          <SettingsSection title="App">
            <SettingsRow
              label="Automatic updates"
              description="Download new versions when they become available."
              htmlFor="anatomy-auto-update"
              control={
                <Switch
                  id="anatomy-auto-update"
                  checked={autoUpdate}
                  onCheckedChange={setAutoUpdate}
                />
              }
            />
            <SettingsRow
              label="Send telemetry"
              description="Anonymous usage data helps improve the application."
              htmlFor="anatomy-telemetry"
              control={
                <Switch id="anatomy-telemetry" checked={telemetry} onCheckedChange={setTelemetry} />
              }
            />
          </SettingsSection>
          <SettingsSection>
            <SettingsRow
              label="Untitled section"
              description="A section without a heading, like General's account card."
              control={
                <Button variant="secondary" size="xs">
                  Manage
                </Button>
              }
            />
          </SettingsSection>
          <SettingsSection title="Custom surface" bare>
            <SettingsCard>
              <SeparatedList gap="1rem" direction="column">
                <SettingsRow
                  label="Bare section"
                  description="Children bring their own surface — custom cards, tile grids."
                  control={<Switch />}
                />
              </SeparatedList>
            </SettingsCard>
          </SettingsSection>
        </div>
      </div>
    </div>
  );
}

export const PageAnatomyStory: Story = {
  name: 'Page anatomy',
  parameters: { layout: 'fullscreen' },
  render: () => <PageAnatomy />,
};

export const AcrossSurfaces: Story = {
  render: () => (
    <Box background="surfaceSunken" rounded="xl" padding="4">
      <Box className={s.maxW2xl} style={storyWidth}>
        <SettingsCard>
          <SeparatedList gap="0.75rem" direction="column">
            <SettingsRow
              label="Compact layout"
              description="Reduce spacing throughout the interface."
              htmlFor="compact-layout"
              control={<Switch id="compact-layout" />}
            />
            <SettingsRow
              label="Restore defaults"
              description="Reset the settings in this section."
              control={
                <Button variant="secondary" size="xs">
                  Restore
                </Button>
              }
            />
          </SeparatedList>
        </SettingsCard>
      </Box>
    </Box>
  ),
};
