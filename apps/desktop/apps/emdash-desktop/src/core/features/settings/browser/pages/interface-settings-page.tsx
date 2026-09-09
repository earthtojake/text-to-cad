import { PageLayout, SettingsSection } from '@emdash/ui/react/patterns';
import FilesSettingsCard from '../components/FilesSettingsCard';
import HiddenToolsSettingsCard from '../components/HiddenToolsSettingsCard';
import InterfaceSettingsCard from '../components/InterfaceSettingsCard';
import KeyboardSettingsCard from '../components/KeyboardSettingsCard';
import SidebarMetadataSettingsCard from '../components/SidebarMetadataSettingsCard';
import TerminalSettingsCard from '../components/TerminalSettingsCard';
import ThemeCard from '../components/ThemeCard';

export function InterfaceSettingsPage() {
  return (
    <div className="space-y-8 pb-4">
      <PageLayout.Header
        sticky
        title="Interface"
        description="Customize the appearance and behavior of the app."
      />
      <SettingsSection title="Color mode" bare>
        <ThemeCard />
      </SettingsSection>
      <SettingsSection title="Terminal" bare>
        <TerminalSettingsCard />
      </SettingsSection>
      <SettingsSection title="Files" bare>
        <FilesSettingsCard />
      </SettingsSection>
      <SettingsSection title="Sidebar" bare>
        <SidebarMetadataSettingsCard />
      </SettingsSection>
      <SettingsSection bare>
        <InterfaceSettingsCard />
      </SettingsSection>
      <SettingsSection title="Keyboard shortcuts" bare>
        <KeyboardSettingsCard />
      </SettingsSection>
      <SettingsSection title="Tools" bare>
        <HiddenToolsSettingsCard />
      </SettingsSection>
    </div>
  );
}
