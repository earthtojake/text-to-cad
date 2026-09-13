import { describe, expect, it } from 'vitest';
import { githubAccountReportingState } from './account-reporting';

describe('githubAccountReportingState', () => {
  it('maps explicit none to the quiet disabled state regardless of accounts', () => {
    expect(githubAccountReportingState({ kind: 'set' }, true)).toEqual({
      kind: 'disabled',
      message: 'GitHub is disabled for this project.',
    });
    expect(githubAccountReportingState({ kind: 'set' }, false)).toEqual({
      kind: 'disabled',
      message: 'GitHub is disabled for this project.',
    });
  });

  it('maps inferred-absent with zero accounts to the connect state', () => {
    expect(
      githubAccountReportingState({ kind: 'inferred', from: 'no host-matching account' }, false)
    ).toEqual({
      kind: 'connect',
      message: 'Connect a GitHub account to get started.',
    });
  });

  it('maps inferred-absent with accounts to the silent default', () => {
    expect(
      githubAccountReportingState({ kind: 'inferred', from: 'no host-matching account' }, true)
    ).toEqual({ kind: 'silent' });
  });

  it('fails closed on an unresolvable pin with a fix message', () => {
    expect(githubAccountReportingState({ kind: 'unresolvable' }, true)).toEqual({
      kind: 'unresolvable',
      message: 'The selected GitHub account is no longer connected.',
    });
  });
});
