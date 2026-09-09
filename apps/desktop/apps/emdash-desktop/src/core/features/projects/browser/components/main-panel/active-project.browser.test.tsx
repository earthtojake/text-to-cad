import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import { ActiveProject } from './active-project';

vi.mock('@core/features/projects/browser/components/task-view/task-list', () => ({
  TaskList: () => <div data-testid="chat-list">Active and archived chats</div>,
}));

beforeAll(() => {
  (
    globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }
  ).IS_REACT_ACT_ENVIRONMENT = true;
});

describe('ActiveProject folder surface', () => {
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

  it('shows chat management without the bespoke engineering dashboard', async () => {
    await act(async () => root.render(<ActiveProject />));

    expect(host.textContent).toContain('Active and archived chats');
    expect(host.textContent).not.toContain('Project home');
    expect(host.textContent).not.toContain('Engineering workspace');
    expect(host.textContent).not.toContain('Documents');
    expect(host.textContent).not.toContain('Materials');
    expect(host.textContent).not.toContain('Manufacturing');
    expect(host.textContent).not.toContain('Project chat');
  });
});
