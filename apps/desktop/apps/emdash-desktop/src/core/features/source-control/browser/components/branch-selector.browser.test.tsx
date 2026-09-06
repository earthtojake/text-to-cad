import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import { BranchSelector } from './branch-selector';

beforeAll(() => {
  (
    globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }
  ).IS_REACT_ACT_ENVIRONMENT = true;
});

describe('BranchSelector degraded actions', () => {
  let host: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    host = document.createElement('div');
    document.body.append(host);
    root = createRoot(host);
  });

  afterEach(async () => {
    await act(async () => root.unmount());
    document.body.replaceChildren();
  });

  it('keeps refresh focusable with a reason and does not present unavailable branches as empty', async () => {
    const onRefresh = vi.fn();
    await act(async () => {
      root.render(
        <BranchSelector
          branches={[]}
          onValueChange={vi.fn()}
          onRefresh={onRefresh}
          refreshDisabledReason="Unavailable while this Project’s Machine is offline."
          observationKind="unavailable"
        />
      );
    });

    const trigger = host.querySelector('button');
    expect(trigger).not.toBeNull();
    await act(async () => {
      trigger?.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    });

    const refresh = document.querySelector<HTMLButtonElement>(
      'button[aria-label="Refresh branches"]'
    );
    expect(refresh?.disabled).toBe(false);
    expect(refresh?.getAttribute('aria-disabled')).toBe('true');
    expect(refresh?.getAttribute('aria-description')).toContain('Machine is offline');
    refresh?.click();
    expect(onRefresh).not.toHaveBeenCalled();
    expect(document.body.textContent).toContain('Branches unavailable');
  });
});
