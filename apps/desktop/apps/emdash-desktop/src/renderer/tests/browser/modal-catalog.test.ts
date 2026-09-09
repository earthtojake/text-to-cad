import type { HostRef } from '@emdash/core/primitives/host/api';
import type { CatalogSkill } from '@emdash/core/primitives/skills/api';
import type { Result } from '@emdash/shared';
import { describe, expect, expectTypeOf, it } from 'vitest';
import { openModal } from '@core/manifests/browser/modal-api';
import { modalCatalog } from '@core/manifests/browser/modal-catalog';
import type { ModalDismissed } from '@core/primitives/modals/react';

const expectedModalIds = [
  'addProjectModal',
  'addRemoteModal',
  'addSshConnModal',
  'agentSignInModal',
  'commandPaletteModal',
  'confirmActionModal',
  'confirmExternalLinkModal',
  'conflictDialog',
  'createConversationModal',
  'createPrModal',
  'createSkillModal',
  'deleteTaskModal',
  'directorySelectorModal',
  'githubConnectModal',
  'githubDeviceFlowModal',
  'linkConversationModal',
  'projectConfigImportModal',
  'promptModal',
  'quitUnsavedChangesModal',
  'relinkProjectModal',
  'renameTaskModal',
  'shareProjectConfigModal',
  'skillDetailModal',
  'taskModal',
  'unsavedChangesModal',
] as const;

function openUnsavedChangesForTypeTest() {
  return openModal('unsavedChangesModal', {
    fileName: 'README.md',
  });
}

function openRemoteCreateSkillForTypeTest(host: HostRef) {
  return openModal('createSkillModal', { host });
}

function openSkillDetailForTypeTest(skill: CatalogSkill) {
  return openModal('skillDetailModal', {
    skill,
    onInstall: async () => true,
    onUninstall: async () => true,
  });
}

describe('modalCatalog', () => {
  it('contains every modal exactly once', () => {
    const catalogIds = modalCatalog.defs.map((definition) => definition.id).sort();

    expect(catalogIds).toEqual([...expectedModalIds].sort());
  });

  it('infers caller props and outcomes from modal ids', () => {
    expectTypeOf<ReturnType<typeof openUnsavedChangesForTypeTest>>().toEqualTypeOf<
      Promise<Result<'save' | 'discard', ModalDismissed>>
    >();
    expectTypeOf<ReturnType<typeof openRemoteCreateSkillForTypeTest>>().toEqualTypeOf<
      Promise<Result<void, ModalDismissed>>
    >();
    expectTypeOf<ReturnType<typeof openSkillDetailForTypeTest>>().toEqualTypeOf<
      Promise<Result<void, ModalDismissed>>
    >();
  });
});
