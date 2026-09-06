import {
  mcpServerFieldCount,
  mcpServerToRegistration,
  registrationToMcpServer,
} from '@emdash/core/primitives/mcp/api';
import { describe, expect, it } from 'vitest';

describe('MCP registration conversion', () => {
  it('preserves enabled state across canonical conversion', () => {
    const server = registrationToMcpServer(
      {
        name: 'inherited',
        enabled: false,
        cwd: './mcp',
        timeout: 10_000,
        oauth: false,
      },
      ['opencode']
    );

    expect(server).toEqual({
      name: 'inherited',
      transport: 'stdio',
      enabled: false,
      cwd: './mcp',
      timeout: 10_000,
      oauth: false,
      providers: ['opencode'],
    });

    expect(mcpServerToRegistration(server)).toEqual({
      name: 'inherited',
      transport: 'stdio',
      enabled: false,
      cwd: './mcp',
      timeout: 10_000,
      oauth: false,
    });
  });

  it('does not treat enabled=true as extra merge signal', () => {
    const implicitDefault = registrationToMcpServer({ name: 'docs', url: 'https://example.com' }, [
      'cursor',
    ]);
    const explicitDefault = registrationToMcpServer(
      { name: 'docs', url: 'https://example.com', enabled: true },
      ['grok']
    );
    const disabled = registrationToMcpServer(
      { name: 'docs', url: 'https://example.com', enabled: false },
      ['opencode']
    );

    expect(mcpServerFieldCount(explicitDefault)).toBe(mcpServerFieldCount(implicitDefault));
    expect(mcpServerFieldCount(disabled)).toBeGreaterThan(mcpServerFieldCount(implicitDefault));
  });
});
