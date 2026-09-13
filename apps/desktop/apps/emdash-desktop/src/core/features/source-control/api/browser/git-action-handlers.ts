import { toast } from '@emdash/ui/react/primitives';
import type { GitRepositoryStore } from '@core/features/source-control/api/browser/stores/git-repository-store';
import {
  formatFetchErrorDetail,
  formatPullErrorDetail,
  formatPushErrorDetail,
} from '@core/features/source-control/api/git-error-messages';
import type { GitCheckoutStore } from '../../browser/stores/git-checkout-store';

export async function runGitFetch(repository: GitRepositoryStore) {
  const result = await repository.fetchRemote();
  if (!result.success) {
    toast.error(`Failed to fetch remote changes: ${formatFetchErrorDetail(result.error)}`);
  }
  return result;
}

export async function runGitPull(git: GitCheckoutStore) {
  const result = await git.pull();
  if (!result.success) {
    toast.error(`Failed to pull changes: ${formatPullErrorDetail(result.error)}`);
  }
  return result;
}

export async function runGitPush(git: GitCheckoutStore) {
  const result = await git.push();
  if (!result.success) {
    toast.error(`Failed to push: ${formatPushErrorDetail(result.error)}`);
  }
  return result;
}

export async function runGitPublishCurrentBranch(git: GitCheckoutStore) {
  const result = await git.publishCurrentBranch();
  if (!result.success) {
    toast.error(`Failed to publish branch: ${formatPushErrorDetail(result.error)}`);
  }
  return result;
}
