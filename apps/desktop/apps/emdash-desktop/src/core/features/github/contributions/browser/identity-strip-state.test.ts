import { describe, expect, it } from 'vitest';
import type { GitHubAccountSummary } from '@core/primitives/github/api';
import type { Resolved } from '@core/primitives/project-settings/api';
import { identityStripBlocksAction, identityStripView } from './identity-strip-state';

function account(accountId: string, login = accountId): GitHubAccountSummary {
  return {
    accountId,
    host: 'github.com',
    login,
    avatarUrl: '',
    credentialSource: 'cli',
    isDefault: false,
  };
}

function resolved(
  value: GitHubAccountSummary | null,
  provenance: Resolved<GitHubAccountSummary | null>['provenance']
): Resolved<GitHubAccountSummary | null> {
  return { value, provenance };
}

describe('identityStripView', () => {
  it('shows a popover override as set for this action, over any resolver outcome', () => {
    const chosen = account('a2');
    const view = identityStripView(resolved(null, { kind: 'unresolvable' }), chosen, [
      account('a1'),
      chosen,
    ]);
    expect(view).toEqual({
      kind: 'account',
      account: chosen,
      provenance: { kind: 'set' },
      isActionOverride: true,
    });
  });

  it('shows the resolved account with its own provenance when nothing is overridden', () => {
    const inferred = account('a1');
    const view = identityStripView(
      resolved(inferred, { kind: 'inferred', from: 'default account' }),
      null,
      [inferred]
    );
    expect(view).toEqual({
      kind: 'account',
      account: inferred,
      provenance: { kind: 'inferred', from: 'default account' },
      isActionOverride: false,
    });
  });

  it('maps explicit none to the quiet disabled row', () => {
    const view = identityStripView(resolved(null, { kind: 'set' }), null, [account('a1')]);
    expect(view.kind).toBe('disabled');
  });

  it('maps zero accounts to the connect empty state', () => {
    const view = identityStripView(
      resolved(null, { kind: 'inferred', from: 'no host-matching account' }),
      null,
      []
    );
    expect(view.kind).toBe('connect');
  });

  it('maps inferred-absent with accounts connected to the no-match row', () => {
    const view = identityStripView(
      resolved(null, { kind: 'inferred', from: 'no host-matching account' }),
      null,
      [account('a1')]
    );
    expect(view.kind).toBe('no-match');
  });

  it('fails closed on an unresolvable pin', () => {
    const view = identityStripView(resolved(null, { kind: 'unresolvable' }), null, [account('a1')]);
    expect(view).toEqual({
      kind: 'unresolvable',
      message: 'The selected GitHub account is no longer connected.',
    });
  });
});

describe('identityStripBlocksAction', () => {
  const accountView = identityStripView(resolved(account('a1'), { kind: 'set' }), null, [
    account('a1'),
  ]);
  const unresolvableView = identityStripView(resolved(null, { kind: 'unresolvable' }), null, []);

  it('never blocks when an account will act', () => {
    expect(identityStripBlocksAction(accountView, true)).toBe(false);
    expect(identityStripBlocksAction(accountView, false)).toBe(false);
  });

  it('blocks accountless outcomes only for actions that genuinely require an account', () => {
    expect(identityStripBlocksAction(unresolvableView, true)).toBe(true);
    expect(identityStripBlocksAction(unresolvableView, false)).toBe(false);
  });
});
