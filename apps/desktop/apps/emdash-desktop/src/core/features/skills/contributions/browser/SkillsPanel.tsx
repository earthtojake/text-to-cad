import { sshConnectionIdOf, type HostRef } from '@emdash/core/primitives/host/api';
import { PageLayout } from '@emdash/ui/react/patterns';
import { useCallback, useState } from 'react';
import { SkillsList } from '@core/features/skills/browser/components/SkillsList';
import { SkillsToolbar } from '@core/features/skills/browser/components/SkillsToolbar';
import { useSkills } from '@core/features/skills/browser/components/useSkills';
import { useOpenModal } from '@core/manifests/browser/modal-api';
import { getHostClient } from '@core/primitives/desktop-host/browser/host-client';

type SkillsPanelProps = {
  host: HostRef;
  header?: { title: string; description: string };
};

export function SkillsPanel({ host, header }: SkillsPanelProps) {
  const [searchQuery, setSearchQuery] = useState('');
  const skills = useSkills({ host, searchQuery });
  const openCreateSkillModal = useOpenModal('createSkillModal');
  const sshConnectionId = sshConnectionIdOf(host);

  const handleOpenTerminal = useCallback(
    (skillPath: string) => {
      void getHostClient().then((client) =>
        client.openIn({
          app: 'terminal',
          path: skillPath,
          isRemote: sshConnectionId !== undefined,
          sshConnectionId,
        })
      );
    },
    [sshConnectionId]
  );

  const toolbar = (
    <SkillsToolbar
      searchQuery={searchQuery}
      onSearchQueryChange={setSearchQuery}
      onRefresh={skills.refresh}
      isRefreshing={skills.isRefreshing}
      onCreateSkill={() => void openCreateSkillModal({ host })}
    />
  );

  return (
    <div className="flex flex-col text-foreground">
      {header ? (
        <PageLayout.Header
          sticky
          title={header.title}
          description={header.description}
          actions={toolbar}
        />
      ) : (
        toolbar
      )}
      <SkillsList skills={skills} onOpenTerminal={handleOpenTerminal} />
    </div>
  );
}
