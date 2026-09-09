import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';

const machineStore = vi.hoisted(() => ({
  connections: [{ id: 'machine-1', name: 'Development machine' }],
  stateFor: () => 'connected',
  renameConnection: vi.fn(),
  connect: vi.fn(),
  retry: vi.fn(),
  disconnect: vi.fn(),
  deleteConnection: vi.fn(),
}));

vi.mock('@emdash/ui/react/components', () => ({
  MachineStatus: () => <span data-machine-status />,
  McpIcon: () => <span data-mcp-icon />,
}));

vi.mock('@core/features/agents/api/browser/client', () => ({
  hostRefFromConnectionId: () => ({ kind: 'remote', connectionId: 'machine-1' }),
}));

vi.mock('@core/features/machines/api/browser/client', () => ({
  getMachinesClient: vi.fn(),
}));

vi.mock('@core/features/machines/contributions/app-stores', () => ({
  getMachinesStore: () => machineStore,
}));

vi.mock('@core/features/mcp/contributions/browser/McpPanel', () => ({
  McpPanel: () => <div>MCP panel</div>,
}));

vi.mock('@core/features/projects/api/browser/stores/project-selectors', () => ({
  asAvailableProject: () => undefined,
  getProjectStore: () => undefined,
}));

vi.mock('@core/features/settings/contributions/browser/agents-page/AgentsPanel', () => ({
  AgentsPanel: () => <div>Agents panel</div>,
}));

vi.mock('@core/features/skills/contributions/browser/SkillsPanel', () => ({
  SkillsPanel: () => <div>Skills panel</div>,
}));

vi.mock('@core/features/workspaces/contributions/browser/workspace-detail-page', () => ({
  WorkspaceDetailPage: () => null,
}));

vi.mock('@core/manifests/browser/modal-api', () => ({
  useOpenModal: () => vi.fn(),
}));

vi.mock('@core/services/hosts/api', () => ({
  isServerUsable: () => true,
}));

vi.mock('../components/host-settings-card', () => ({
  HostSettingsCard: () => <div>Host settings</div>,
}));

vi.mock('../components/machine-connection-card', () => ({
  MachineConnectionRow: () => <div>System panel</div>,
}));

vi.mock('../components/machine-conversations-list', () => ({
  MachineConversationsList: () => <div>Conversations panel</div>,
}));

vi.mock('../components/machine-resources', () => ({
  ResourceUtilizationRow: () => null,
}));

vi.mock('../components/machine-status-kind', () => ({
  deriveMachineStatusKind: () => 'idle',
}));

vi.mock('../components/machine-system-dependencies', () => ({
  MachineSystemDependenciesCard: () => null,
}));

vi.mock('../components/workspace-server-card', () => ({
  WorkspaceRuntimeRow: () => null,
}));

vi.mock('../components/workspaces-list-view', () => ({
  WorkspacesListView: () => <div>Workspaces panel</div>,
}));

vi.mock('../use-host-server-state', () => ({
  useHostServerState: () => ({ loading: false, state: { kind: 'ready' } }),
}));

vi.mock('../use-machine-metrics', () => ({
  useMachineMetrics: () => undefined,
}));

vi.mock('../use-machine-status-kind', () => ({
  useMachineAvailability: () => undefined,
}));

import { MachineDetailsPage } from './machine-details-page';

beforeAll(() => {
  (
    globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }
  ).IS_REACT_ACT_ENVIRONMENT = true;
});

describe('MachineDetailsPage tabs', () => {
  let host: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    host = document.createElement('div');
    document.body.appendChild(host);
    root = createRoot(host);
  });

  afterEach(async () => {
    await act(async () => root.unmount());
    host.remove();
  });

  it('switches machine sections and keeps the panel labelled by the active pill', async () => {
    await act(async () => {
      root.render(
        <MachineDetailsPage
          path={['machine-1']}
          detailId="machine-1"
          openDetail={vi.fn()}
          closeDetail={vi.fn()}
        />
      );
    });

    const tabs = [...host.querySelectorAll<HTMLButtonElement>('[role="tab"]')];
    const system = tabs.find((tab) => tab.getAttribute('aria-label') === 'System');
    const workspaces = tabs.find((tab) => tab.getAttribute('aria-label') === 'Workspaces');
    const panel = host.querySelector<HTMLElement>('[role="tabpanel"]');

    expect(tabs).toHaveLength(6);
    expect(system?.getAttribute('aria-selected')).toBe('true');
    expect(panel?.getAttribute('aria-labelledby')).toBe('machine-details-panel-tab-system');
    expect(panel?.textContent).toContain('System panel');

    await act(async () => workspaces?.click());

    expect(workspaces?.getAttribute('aria-selected')).toBe('true');
    expect(panel?.getAttribute('aria-labelledby')).toBe('machine-details-panel-tab-workspaces');
    expect(panel?.textContent).toContain('Workspaces panel');
  });
});
