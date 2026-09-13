import { CollectionToolbar, CollectionView, PageLayout } from '@emdash/ui/react/patterns';
import { Button } from '@emdash/ui/react/primitives';
import { PlusIcon, ServerIcon } from 'lucide-react';
import { observer } from 'mobx-react-lite';
import { useState } from 'react';
import { getMachinesStore } from '@core/features/machines/contributions/app-stores';
import { useOpenModal } from '@core/manifests/browser/modal-api';
import type { SettingsPageProps } from '@core/primitives/settings/api/page-contribution';
import type { ConnectionState } from '@core/primitives/ssh/api';
import { MachineListRow } from '../components/machine-list-row';
import { createMachinesListView, type MachinesListViewModel } from '../machines-list-model';

function isRecentlyUsed(state: ConnectionState): boolean {
  return state === 'connected' || state === 'connecting' || state === 'reconnecting';
}

export const MachinesSettingsPage = observer(function MachinesSettingsPage({
  openDetail,
}: SettingsPageProps) {
  const machinesStore = getMachinesStore();
  const openMachineModal = useOpenModal('addSshConnModal');
  // The machines store is MobX-observable, so the view's source getter reads it
  // directly and the list pipeline re-derives on store changes — no bridge needed.
  const [view] = useState(() =>
    createMachinesListView({
      getMachines: () => getMachinesStore().connections,
      isRecentlyUsed: (machine) => isRecentlyUsed(getMachinesStore().stateFor(machine.id)),
    })
  );

  const openCreateModal = () => {
    void openMachineModal({ dismissControl: 'close' });
  };

  return (
    <div className="flex min-h-0 flex-col gap-4">
      <PageLayout.Header
        sticky
        title="Machines"
        description="Manage reusable machines for remote projects."
      />
      <view.Root>
        <CollectionView
          view={view}
          renderRow={(machine) => <MachineListRow machine={machine} />}
          density="compact"
          toolbar={<MachinesToolbar view={view} onAdd={openCreateModal} />}
          onItemClick={(machine) => openDetail(machine.id)}
          emptySlot={<MachinesEmptyState hasMachines={machinesStore.connections.length > 0} />}
        />
      </view.Root>
    </div>
  );
});

const MachinesToolbar = observer(function MachinesToolbar({
  view,
  onAdd,
}: {
  view: MachinesListViewModel;
  onAdd: () => void;
}) {
  const search = view.useSearch();
  return (
    <CollectionToolbar
      searchValue={search.query}
      onSearchValueChange={search.setQuery}
      searchPlaceholder="Search machines…"
      actions={
        <Button type="button" variant="primary" onClick={onAdd}>
          <PlusIcon />
          Add machine
        </Button>
      }
    />
  );
});

function MachinesEmptyState({ hasMachines }: { hasMachines: boolean }) {
  return (
    <div className="flex min-h-48 flex-col items-center justify-center p-8 text-center">
      <ServerIcon className="mb-3 size-8 text-foreground-passive" />
      <div className="text-sm text-foreground">
        {hasMachines ? 'No machines match your search' : 'No machines'}
      </div>
      <p className="mt-1 max-w-sm text-xs text-foreground-passive">
        {hasMachines
          ? 'Try a different name, host, or username.'
          : 'Add a machine to create and manage remote projects.'}
      </p>
    </div>
  );
}
