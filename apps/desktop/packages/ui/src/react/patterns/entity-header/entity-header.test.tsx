/**
 * @vitest-environment jsdom
 */
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { EntityHeader } from './entity-header';

afterEach(cleanup);

describe('EntityHeader', () => {
  it('renders the identity and action slots in a semantic header', () => {
    const { container } = render(
      <EntityHeader
        icon={<span data-testid="identity-icon" />}
        title={<h1>Emdash</h1>}
        actions={<button type="button">Actions</button>}
      />
    );

    expect(container.querySelector('header[data-slot="entity-header"]')).not.toBeNull();
    expect(screen.getByTestId('identity-icon')).not.toBeNull();
    expect(screen.getByRole('heading', { level: 1, name: 'Emdash' })).not.toBeNull();
    expect(screen.getByRole('button', { name: 'Actions' })).not.toBeNull();
  });

  it('keeps the machine identity and actions while its title becomes an editor', () => {
    const icon = <span data-testid="machine-status" />;
    const actions = <button type="button">Machine actions</button>;
    const { rerender } = render(
      <EntityHeader icon={icon} title={<h1>Development machine</h1>} actions={actions} />
    );

    rerender(
      <EntityHeader
        icon={icon}
        title={<input aria-label="Machine name" value="Development machine" readOnly />}
        actions={actions}
      />
    );

    expect(screen.getByTestId('machine-status')).not.toBeNull();
    expect(screen.queryByRole('heading')).toBeNull();
    expect(screen.getByRole('textbox', { name: 'Machine name' })).not.toBeNull();
    expect(screen.getByRole('button', { name: 'Machine actions' })).not.toBeNull();
  });
});
