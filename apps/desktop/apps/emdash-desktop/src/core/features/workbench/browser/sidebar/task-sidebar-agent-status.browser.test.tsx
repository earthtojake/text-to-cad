import '@emdash/ui/style.css';
import React, { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeAll, beforeEach, describe, expect, it } from 'vitest';
import { page } from 'vitest/browser';
import { SidebarAgentStatusLabel } from './task-sidebar-agent-status';

beforeAll(() => {
  (
    globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }
  ).IS_REACT_ACT_ENVIRONMENT = true;
});

describe('SidebarAgentStatusLabel', () => {
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

  it('explains every non-idle task state without relying on a colored dot', async () => {
    await act(async () => {
      root.render(
        <>
          <SidebarAgentStatusLabel status="working" />
          <SidebarAgentStatusLabel status="awaiting-input" />
          <SidebarAgentStatusLabel status="error" />
          <SidebarAgentStatusLabel status="completed" />
        </>
      );
    });

    expect(page.getByRole('status', { name: 'Working' })).toHaveTextContent('Working');
    expect(page.getByRole('status', { name: 'Needs input' })).toHaveTextContent('Needs input');
    expect(page.getByRole('status', { name: 'Failed' })).toHaveTextContent('Failed');
    expect(page.getByRole('status', { name: 'Done' })).toHaveTextContent('Done');
  });
});
