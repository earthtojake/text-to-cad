import { PageLayout, SettingsSection } from '@emdash/ui/react/patterns';
import NotificationSettingsCard from '../components/NotificationSettingsCard';
import {
  AutoApproveByDefaultRow,
  AutoGenerateTaskNamesRow,
  AutoTrustWorktreesRow,
  CreateBranchAndWorktreeRow,
  DeleteBranchByDefaultRow,
  EnableTmuxRow,
  IncludeIssueContextByDefaultRow,
  PreserveTaskNameCapitalizationRow,
} from '../components/TaskSettingsRows';
import TelemetryCard from '../components/TelemetryCard';
import { UpdateCard } from '../components/UpdateCard';

export function GeneralSettingsPage() {
  return (
    <div className="space-y-8 pb-10">
      <PageLayout.Header
        sticky
        draggable
        title="General"
        description="Manage app updates, notifications, and engineering preferences."
      />
      <SettingsSection title="App">
        <UpdateCard />
        <TelemetryCard />
      </SettingsSection>
      <SettingsSection title="Notifications" bare>
        <NotificationSettingsCard />
      </SettingsSection>
      <SettingsSection title="Preferences">
        <AutoGenerateTaskNamesRow />
        <AutoApproveByDefaultRow />
        <AutoTrustWorktreesRow />
        <CreateBranchAndWorktreeRow />
        <DeleteBranchByDefaultRow />
        <PreserveTaskNameCapitalizationRow />
        <IncludeIssueContextByDefaultRow />
        <EnableTmuxRow />
      </SettingsSection>
    </div>
  );
}
