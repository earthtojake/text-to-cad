import { describe, expect, it } from 'vitest';
import { resolveTaskBranchName } from './resolve-task-branch-name';

describe('resolveTaskBranchName', () => {
  it('uses Linear branchName as-is when available', () => {
    const branchName = resolveTaskBranchName({
      rawBranch: 'linear-issue-branch-name-creation',
      branchPrefix: 'emdash',
      suffix: 'abc12',
      appendRandomSuffix: true,
      linkedIssue: {
        provider: 'linear',
        url: 'https://linear.app/general-action/issue/GEN-626',
        title: 'Linear issue branch name creation',
        identifier: 'GEN-626',
        branchName: 'jona/gen-626-linear-issue-branch-name-creation',
      },
    });

    expect(branchName).toBe('jona/gen-626-linear-issue-branch-name-creation');
  });

  it('keeps Linear branch names unsuffixed when Linear branchName is absent', () => {
    const branchName = resolveTaskBranchName({
      rawBranch: 'linear-issue-branch-name-creation',
      branchPrefix: 'emdash',
      suffix: 'abc12',
      appendRandomSuffix: true,
      linkedIssue: {
        provider: 'linear',
        url: 'https://linear.app/general-action/issue/GEN-626',
        title: 'Linear issue branch name creation',
        identifier: 'GEN-626',
      },
    });

    expect(branchName).toBe('emdash/linear-issue-branch-name-creation');
  });

  it('keeps the existing format for non-Linear issues', () => {
    const branchName = resolveTaskBranchName({
      rawBranch: 'bugfix-login',
      branchPrefix: 'emdash',
      suffix: 'xyz99',
      appendRandomSuffix: true,
      linkedIssue: {
        provider: 'jira',
        url: 'https://example.atlassian.net/browse/APP-42',
        title: 'Fix login bug',
        identifier: 'APP-42',
        branchName: 'someone/app-42-fix-login-bug',
      },
    });

    expect(branchName).toBe('emdash/bugfix-login-xyz99');
  });

  it('omits only the random suffix when disabled', () => {
    const branchName = resolveTaskBranchName({
      rawBranch: 'bugfix-login',
      branchPrefix: 'emdash',
      suffix: 'xyz99',
      appendRandomSuffix: false,
    });

    expect(branchName).toBe('emdash/bugfix-login');
  });

  it('omits the random suffix when explicitly disabled for a provider flow', () => {
    const branchName = resolveTaskBranchName({
      rawBranch: 'bugfix-login',
      branchPrefix: 'emdash',
      suffix: 'xyz99',
      appendRandomSuffix: true,
      disableRandomSuffix: true,
    });

    expect(branchName).toBe('emdash/bugfix-login');
  });

  it('can create the raw task name when suffix and prefix are disabled', () => {
    const branchName = resolveTaskBranchName({
      rawBranch: 'bugfix-login',
      branchPrefix: '',
      suffix: 'xyz99',
      appendRandomSuffix: false,
    });

    expect(branchName).toBe('bugfix-login');
  });
});
