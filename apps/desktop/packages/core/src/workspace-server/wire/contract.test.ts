import { describe, expect, it } from 'vitest';
import { workspaceWireContract } from './contract';

describe('workspaceWireContract', () => {
  it('mounts every worker-backed runtime expected by the aggregate controller', () => {
    expect(workspaceWireContract.fileSearch.searchContent.kind).toBe('liveJob');
    expect(workspaceWireContract.terminals.start.kind).toBe('procedure');
  });

  it('mounts the ACP contract under the acp domain without changing protocol shape elsewhere', () => {
    expect(workspaceWireContract.acp.start.kind).toBe('procedure');
    expect(workspaceWireContract.acp.sessions.kind).toBe('liveModel');
    expect(workspaceWireContract.acp.sessions.id).toBe('acp.sessions');
    expect(workspaceWireContract.acp.terminalOutput.kind).toBe('liveLog');
    expect(workspaceWireContract.acp.terminalOutput.id).toBe('acp.terminalOutput');
  });

  it('mounts TUI agents under the tuiAgents domain', () => {
    expect(workspaceWireContract.tuiAgents.start.kind).toBe('procedure');
    expect(workspaceWireContract.tuiAgents.resume.kind).toBe('procedure');
    expect(workspaceWireContract.tuiAgents.output.kind).toBe('liveLog');
    expect(workspaceWireContract.tuiAgents.output.id).toBe('tuiAgents.output');
    expect(workspaceWireContract.tuiAgents.sessions.kind).toBe('liveModel');
    expect(workspaceWireContract.tuiAgents.sessions.id).toBe('tuiAgents.sessions');
    expect(workspaceWireContract.tuiAgents.agentStates.kind).toBe('liveModel');
    expect(workspaceWireContract.tuiAgents.agentStates.id).toBe('tuiAgents.agentStates');
  });

  it('serves disk-usage measurement from the registry', () => {
    expect(workspaceWireContract.workspaceRegistry.measureUsage.kind).toBe('procedure');
  });

  it('does not mount the retired workspace runtimes', () => {
    expect('workspace' in workspaceWireContract).toBe(false);
    expect('workspaceHost' in workspaceWireContract).toBe(false);
  });

  it('mounts port forwards under the portForwards domain', () => {
    expect(workspaceWireContract.portForwards.inspect.kind).toBe('procedure');
  });
});
