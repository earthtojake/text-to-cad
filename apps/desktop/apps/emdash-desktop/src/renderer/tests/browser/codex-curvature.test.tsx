import '@emdash/ui/style.css';
import { ChatComposer, Pill } from '@emdash/ui/react/components';
import { Button, Checkbox, DropdownMenu, Input, InputGroup } from '@emdash/ui/react/primitives';
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeAll, beforeEach, describe, expect, it } from 'vitest';
import { page } from 'vitest/browser';
import '../../index.css';
import '../../design-system.css';

beforeAll(() => {
  (
    globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }
  ).IS_REACT_ACT_ENVIRONMENT = true;
});

describe.each(['emlight', 'emdark'] as const)('Codex curvature overlay (%s)', (themeClass) => {
  let host: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    document.documentElement.classList.add(themeClass);
    host = document.createElement('div');
    document.body.appendChild(host);
    root = createRoot(host);
  });

  afterEach(async () => {
    await act(async () => root.unmount());
    document.documentElement.classList.remove(themeClass);
    host.remove();
  });

  it('rounds controls, pills, checkboxes, and the composer by role', async () => {
    await act(async () => {
      root.render(
        <div className={themeClass} data-testid="theme-root">
          <Button data-testid="button">Continue</Button>
          <Button data-testid="button-xs" variant="ghost" size="xs">
            Compact
          </Button>
          <Button data-testid="button-sm" variant="secondary" size="sm" aria-pressed="true">
            Pressed
          </Button>
          <Button data-testid="button-lg" variant="primary" size="lg">
            Large
          </Button>
          <button data-testid="utility-sm" className="rounded-sm hover:bg-background-secondary">
            Utility small
          </button>
          <button data-testid="utility-md" className="rounded-md hover:bg-background-secondary">
            Utility medium
          </button>
          <button data-testid="utility-lg" className="rounded-lg hover:bg-background-secondary">
            Utility large
          </button>
          <Input data-testid="small-input" size="sm" />
          <InputGroup.Root data-testid="input-group">
            <InputGroup.Input aria-label="Grouped input" />
          </InputGroup.Root>
          <Pill data-testid="pill">Ready</Pill>
          <Checkbox aria-label="Select task" />
          <DropdownMenu.Root>
            <DropdownMenu.Trigger>Open menu</DropdownMenu.Trigger>
            <DropdownMenu.Content>
              <DropdownMenu.Group>
                <DropdownMenu.Label>Options</DropdownMenu.Label>
                <DropdownMenu.Item data-testid="menu-item">One</DropdownMenu.Item>
              </DropdownMenu.Group>
            </DropdownMenu.Content>
          </DropdownMenu.Root>
          <ChatComposer onSubmit={() => {}} />
        </div>
      );
    });

    const themeRoot = host.querySelector<HTMLElement>('[data-testid="theme-root"]')!;
    const button = host.querySelector<HTMLElement>('[data-testid="button"]')!;
    const smallInput = host.querySelector<HTMLElement>('[data-testid="small-input"]')!;
    const inputGroup = host.querySelector<HTMLElement>('[data-testid="input-group"]')!;
    const pill = host.querySelector<HTMLElement>('[data-testid="pill"]')!;
    const checkbox = host.querySelector<HTMLElement>('[data-slot="checkbox"]')!;
    const sendButton = host.querySelector<HTMLElement>('[aria-label="Send message"]')!;
    const composerShell = sendButton.parentElement!.parentElement!.parentElement!;
    expect(getComputedStyle(themeRoot).getPropertyValue('--chat-radius-xl').trim()).toBe('18px');
    expect(getComputedStyle(button).borderRadius).toBe('10px');
    expect(getComputedStyle(button).height).toBe('32px');
    expect(
      getComputedStyle(host.querySelector<HTMLElement>('[data-testid="button-xs"]')!).borderRadius
    ).toBe('8px');
    expect(
      getComputedStyle(host.querySelector<HTMLElement>('[data-testid="button-sm"]')!).borderRadius
    ).toBe('8px');
    expect(
      getComputedStyle(host.querySelector<HTMLElement>('[data-testid="button-lg"]')!).borderRadius
    ).toBe('10px');
    expect(getComputedStyle(smallInput).height).toBe('28px');
    expect(getComputedStyle(smallInput).fontSize).toBe('13px');
    expect(getComputedStyle(inputGroup).height).toBe('32px');
    expect(getComputedStyle(pill).borderRadius).toBe('9999px');
    expect(getComputedStyle(checkbox).borderRadius).toBe('4px');
    expect(getComputedStyle(sendButton).borderRadius).toBe('9999px');
    expect(getComputedStyle(sendButton).width).toBe('28px');
    expect(getComputedStyle(sendButton).height).toBe('28px');
    expect(getComputedStyle(composerShell).borderRadius).toBe('20px');
    const utilityRadii = [
      ['utility-sm', '6px'],
      ['utility-md', '8px'],
      ['utility-lg', '10px'],
    ] as const;
    for (const [testId, expectedRadius] of utilityRadii) {
      const locator = page.getByTestId(testId);
      const element = locator.query() as HTMLElement;
      expect(getComputedStyle(element).borderRadius).toBe(expectedRadius);
      await locator.hover();
      expect(getComputedStyle(element).borderRadius).toBe(expectedRadius);
    }

    for (const testId of ['button', 'button-xs', 'button-sm', 'button-lg']) {
      const locator = page.getByTestId(testId);
      const element = locator.query() as HTMLElement;
      const restRadius = getComputedStyle(element).borderRadius;
      await locator.hover();
      expect(getComputedStyle(element).borderRadius).toBe(restRadius);
    }

    await page.getByText('Open menu').click();
    const menu = document.querySelector<HTMLElement>('[data-slot="dropdown-menu-content"]')!;
    const menuLabel = document.querySelector<HTMLElement>('[data-slot="dropdown-menu-label"]')!;
    const menuItem = document.querySelector<HTMLElement>('[data-slot="dropdown-menu-item"]')!;
    expect(getComputedStyle(menu).borderRadius).toBe('8px');
    expect(getComputedStyle(menu).padding).toBe('4px');
    expect(getComputedStyle(menuItem).minHeight).toBe('28px');
    expect(getComputedStyle(menuItem).borderRadius).toBe('6px');
    expect(getComputedStyle(menuLabel).textTransform).toBe('none');

    const menuItemLocator = page.getByTestId('menu-item');
    await menuItemLocator.hover();
    expect(getComputedStyle(menuItem).borderRadius).toBe('6px');
  });
});
