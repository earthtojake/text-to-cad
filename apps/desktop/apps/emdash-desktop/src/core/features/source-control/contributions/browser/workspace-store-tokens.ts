import { scopedStoreToken } from '@core/primitives/scoped-stores/browser';
import type { DiffTabManager } from '../../browser/diff-view/stores/diff-tab-manager';
import type { GitCheckoutStore } from '../../browser/stores/git-checkout-store';

export const gitCheckoutStoreToken = scopedStoreToken<GitCheckoutStore>('source-control.checkout');
export const diffTabManagerStoreToken = scopedStoreToken<DiffTabManager>(
  'source-control.diff-tabs'
);
