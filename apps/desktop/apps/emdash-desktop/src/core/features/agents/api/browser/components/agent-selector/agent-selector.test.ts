import { asAgentProviderId } from '@emdash/plugins/agents/types';
import { describe, expect, it } from 'vitest';
import type { AgentCapabilities } from '@core/primitives/agents/api';
import { getHostDependencyErrorMessage } from '@core/primitives/host-dependencies/browser/error-message';
import { getAgentInstallActionState } from './agent-install';
import {
  buildAgentGroups,
  canInstallAgentOption,
  getAssumedInstalledAgents,
  getInstallButtonState,
  isComboboxOptionDisabled,
} from './agent-selector-options';

const capabilities = (acpKind: string = 'none'): AgentCapabilities => ({
  acp: { kind: acpKind },
  auth: { kind: 'none' },
  hostDependency: { updates: { kind: 'none' } },
  models: { kind: 'none' },
  effort: { kind: 'none' },
  prompt: { kind: 'none' },
  sessions: { kind: 'none' },
  autoApprove: { kind: 'none' },
  hooks: { kind: 'none' },
  mcp: { kind: 'none' },
  plugins: { kind: 'none' },
  trust: { kind: 'none' },
});

const agents = [
  { id: 'codex', name: 'Codex', capabilities: capabilities('supported') },
  { id: 'claude', name: 'Claude Code', capabilities: capabilities('supported') },
  { id: 'qwen', name: 'Qwen Code', capabilities: capabilities() },
];

const agent = asAgentProviderId;

describe('buildAgentGroups', () => {
  it('marks installed agents selectable and uninstalled agents disabled', () => {
    const groups = buildAgentGroups(agents, ['codex']);

    expect(groups.find((group) => group.value === 'installed')?.items).toEqual(
      expect.arrayContaining([expect.objectContaining({ agentId: 'codex', disabled: false })])
    );
    expect(groups.find((group) => group.value === 'not-installed')?.items).toEqual(
      expect.arrayContaining([expect.objectContaining({ agentId: 'claude', disabled: true })])
    );
  });

  it('keeps the selected agent installed while availability is still unknown', () => {
    const groups = buildAgentGroups(agents, [], ['codex']);

    expect(groups.find((group) => group.value === 'installed')?.items).toEqual([
      expect.objectContaining({ agentId: 'codex', disabled: false }),
    ]);
    expect(groups.find((group) => group.value === 'not-installed')?.items).not.toEqual(
      expect.arrayContaining([expect.objectContaining({ agentId: 'codex' })])
    );
  });

  it('keeps installing agents in the not-installed group until install resolves', () => {
    const groups = buildAgentGroups(agents, ['codex', 'claude'], [], new Set([agent('claude')]));

    expect(groups.find((group) => group.value === 'installed')?.items).toEqual(
      expect.arrayContaining([expect.objectContaining({ agentId: 'codex', disabled: false })])
    );
    expect(groups.find((group) => group.value === 'installed')?.items).not.toEqual(
      expect.arrayContaining([expect.objectContaining({ agentId: 'claude' })])
    );
    expect(groups.find((group) => group.value === 'not-installed')?.items).toEqual(
      expect.arrayContaining([expect.objectContaining({ agentId: 'claude', disabled: true })])
    );
  });

  it('marks ACP-capable agent options', () => {
    const groups = buildAgentGroups(agents, ['codex']);

    const codex = groups
      .find((group) => group.value === 'installed')
      ?.items.find((option) => option.agentId === 'codex');
    const qwen = groups
      .find((group) => group.value === 'not-installed')
      ?.items.find((option) => option.agentId === 'qwen');

    expect(codex).toEqual(expect.objectContaining({ supportsAcp: true }));
    expect(qwen).toEqual(expect.objectContaining({ supportsAcp: false }));
  });

  it('does not assume an installing selected agent is installed', () => {
    const groups = buildAgentGroups(agents, [], ['claude'], new Set([agent('claude')]));

    expect(groups.find((group) => group.value === 'installed')?.items).toBeUndefined();
    expect(groups.find((group) => group.value === 'not-installed')?.items).toEqual(
      expect.arrayContaining([expect.objectContaining({ agentId: 'claude', disabled: true })])
    );
  });

  it('keeps the selected agent installed when dependency data is partial', () => {
    const assumedInstalledAgents = getAssumedInstalledAgents(agent('codex'), {
      claude: {
        id: 'claude',
        category: 'agent',
        status: 'available',
        version: '1.0.0',
        path: '/bin/claude',
        checkedAt: 1,
      },
    });
    const groups = buildAgentGroups(agents, ['claude'], assumedInstalledAgents);

    expect(groups.find((group) => group.value === 'installed')?.items).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ agentId: 'claude', disabled: false }),
        expect.objectContaining({ agentId: 'codex', disabled: false }),
      ])
    );
    expect(groups.find((group) => group.value === 'not-installed')?.items).not.toEqual(
      expect.arrayContaining([expect.objectContaining({ agentId: 'codex' })])
    );
  });

  it('keeps inline-install rows disabled while allowing install actions', () => {
    const item = buildAgentGroups(agents, ['codex'])
      .find((group) => group.value === 'not-installed')
      ?.items.find((option) => option.agentId === 'claude');

    expect(item).toBeDefined();
    expect(canInstallAgentOption(item!, true)).toBe(true);
    expect(isComboboxOptionDisabled(item!)).toBe(true);
    expect(getInstallButtonState(item!, true, new Set())).toEqual({
      render: true,
      disabled: false,
      installing: false,
      label: 'Install Claude Code',
    });
  });

  it('disables installed agents with custom reasons without showing install actions', () => {
    const item = buildAgentGroups(agents, ['codex'], [], new Set(), (agent) =>
      agent.id === 'codex' ? 'Not available here' : null
    )
      .find((group) => group.value === 'installed')
      ?.items.find((option) => option.agentId === 'codex');

    expect(item).toEqual(
      expect.objectContaining({
        agentId: 'codex',
        disabled: true,
        disabledReason: 'Not available here',
      })
    );
    expect(canInstallAgentOption(item!, true)).toBe(false);
    expect(isComboboxOptionDisabled(item!)).toBe(true);
    expect(getInstallButtonState(item!, true, new Set()).render).toBe(false);
  });

  it('maps permission install errors to friendly copy', () => {
    expect(
      getHostDependencyErrorMessage({
        type: 'permission-denied',
        id: 'codex',
        message: 'User does not have sufficient permissions.',
        output: 'permission denied',
        exitCode: 243,
      })
    ).toBe('User does not have sufficient permissions.');
  });

  it('maps missing installer errors to friendly copy', () => {
    expect(
      getHostDependencyErrorMessage({
        type: 'installer-missing',
        id: 'codex',
        tool: 'npm',
        method: 'npm',
      })
    ).toBe(
      'The installer `npm` is not installed on this machine, so codex cannot be installed. Install `npm` or choose a different install method.'
    );
  });

  it('supports non-combobox install actions', () => {
    expect(
      getAgentInstallActionState({
        agentName: 'Cursor',
        canInstall: true,
        isInstalled: false,
        isInstalling: true,
      })
    ).toEqual({
      render: true,
      disabled: true,
      installing: true,
      label: 'Install Cursor',
    });

    expect(
      getAgentInstallActionState({
        agentName: 'Cursor',
        canInstall: true,
        isInstalled: true,
        isInstalling: false,
      }).render
    ).toBe(false);
  });

  it('only disables the actively installing agent button', () => {
    const notInstalledItems =
      buildAgentGroups(agents, ['codex']).find((group) => group.value === 'not-installed')?.items ??
      [];
    const claude = notInstalledItems.find((option) => option.agentId === 'claude')!;
    const qwen = notInstalledItems.find((option) => option.agentId === 'qwen')!;

    expect(getInstallButtonState(claude, true, new Set([agent('claude')]))).toEqual({
      render: true,
      disabled: true,
      installing: true,
      label: 'Install Claude Code',
    });
    expect(getInstallButtonState(qwen, true, new Set(['claude']))).toEqual({
      render: true,
      disabled: false,
      installing: false,
      label: 'Install Qwen Code',
    });
  });

  it('supports multiple active installs at the same time', () => {
    const notInstalledItems =
      buildAgentGroups(agents, ['codex']).find((group) => group.value === 'not-installed')?.items ??
      [];
    const claude = notInstalledItems.find((option) => option.agentId === 'claude')!;
    const qwen = notInstalledItems.find((option) => option.agentId === 'qwen')!;

    expect(getInstallButtonState(claude, true, new Set([agent('claude'), agent('qwen')]))).toEqual({
      render: true,
      disabled: true,
      installing: true,
      label: 'Install Claude Code',
    });
    expect(getInstallButtonState(qwen, true, new Set([agent('claude'), agent('qwen')]))).toEqual({
      render: true,
      disabled: true,
      installing: true,
      label: 'Install Qwen Code',
    });
  });
});
