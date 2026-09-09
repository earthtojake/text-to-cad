import { PageLayout } from '@emdash/ui/react/patterns';
import { BrowserSettingsCard } from '../components/BrowserSettingsCard';

export function BrowserSettingsPage() {
  return (
    <div className="space-y-8">
      <PageLayout.Header
        sticky
        title="Browser"
        description="Manage browser profiles and their stored logins."
      />
      <BrowserSettingsCard />
    </div>
  );
}
