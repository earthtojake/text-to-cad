import { PageLayout } from '@emdash/ui/react/patterns';
import { MachineConversationsList } from '../components/machine-conversations-list';

export function ConversationsSettingsPage() {
  return (
    <div className="space-y-8 pb-4">
      <PageLayout.Header
        sticky
        title="Conversations"
        description="Every conversation record on this machine, including ones no longer linked to a task."
      />
      <MachineConversationsList scope={{ kind: 'local' }} hostReachable />
    </div>
  );
}
