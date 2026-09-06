import { PageLayout, SettingsSection } from '@emdash/ui/react/patterns';
import RepositorySettingsCard from '../components/RepositorySettingsCard';

export function RepositorySettingsPage() {
  return (
    <div className="space-y-8">
      <PageLayout.Header
        sticky
        title="Repository"
        description="Configure repository and branch settings."
      />
      <SettingsSection title="Branches" bare>
        <RepositorySettingsCard />
      </SettingsSection>
    </div>
  );
}
