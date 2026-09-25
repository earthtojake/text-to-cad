import React from 'react';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, expect, it } from 'vitest';
import { DropdownMenu, DropdownMenuCheckboxItem, DropdownMenuContent, DropdownMenuRadioGroup, DropdownMenuRadioItem, DropdownMenuTrigger } from './dropdown-menu.jsx';
Object.assign(globalThis, { React });
afterEach(cleanup);

it('checkbox and radio items carry their check on the right, with no left gutter', () => {
  render(<DropdownMenu open><DropdownMenuTrigger>Menu</DropdownMenuTrigger><DropdownMenuContent>
    <DropdownMenuRadioGroup value="b"><DropdownMenuRadioItem value="a">Alpha</DropdownMenuRadioItem><DropdownMenuRadioItem value="b">Beta</DropdownMenuRadioItem></DropdownMenuRadioGroup>
    <DropdownMenuCheckboxItem checked>Loop</DropdownMenuCheckboxItem>
  </DropdownMenuContent></DropdownMenu>);
  for (const name of ['Alpha', 'Beta', 'Loop']) {
    const item = screen.getByRole(name === 'Loop' ? 'menuitemcheckbox' : 'menuitemradio', { name });
    expect(item.className).toMatch(/\bpl-2\b/);
    expect(item.className).toMatch(/\bpr-8\b/);
    expect(item.querySelector('span.absolute')!.className).toMatch(/\bright-2\b/);
  }
  // The chosen one shows a check, never a radio dot.
  expect(screen.getByRole('menuitemradio', { name: 'Beta' }).querySelector('svg.lucide-check')).not.toBeNull();
  expect(document.querySelector('svg.lucide-circle')).toBeNull();
});
