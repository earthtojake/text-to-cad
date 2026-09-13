import { systemClock, type Clock } from '@emdash/shared/scheduling';
import { makeAutoObservable, observable } from 'mobx';
import type { PrCheckoutDrift, PullRequest } from '@core/services/pull-requests/api';

export type TaskPrAssociationState =
  | { readonly kind: 'unknown' }
  | { readonly kind: 'none'; readonly observedAt: number }
  | {
      readonly kind: 'associated';
      readonly pullRequests: readonly PullRequest[];
      readonly observedAt: number;
    };

/** Task-lifetime ownership boundary for renderer-derived PR association state. */
export class TaskPrAssociationStore {
  private _state: TaskPrAssociationState = { kind: 'unknown' };
  private _checkoutDrift: PrCheckoutDrift = { kind: 'unknown' };

  constructor(private readonly clock: Clock = systemClock) {
    makeAutoObservable<TaskPrAssociationStore, '_state' | '_checkoutDrift' | 'clock'>(this, {
      _state: observable.ref,
      _checkoutDrift: observable.ref,
      clock: false,
    });
  }

  get state(): TaskPrAssociationState {
    return this._state;
  }

  get pullRequests(): readonly PullRequest[] {
    return this._state.kind === 'associated' ? this._state.pullRequests : [];
  }

  get checkoutDrift(): PrCheckoutDrift {
    return this._checkoutDrift;
  }

  setAssociation(pullRequests: readonly PullRequest[], checkoutDrift: PrCheckoutDrift): void {
    const observedAt = this.clock.now();
    this._state =
      pullRequests.length > 0
        ? { kind: 'associated', pullRequests: [...pullRequests], observedAt }
        : { kind: 'none', observedAt };
    this._checkoutDrift = checkoutDrift;
  }

  updateAssociatedPr(pullRequest: PullRequest): void {
    if (this._state.kind !== 'associated') return;
    const index = this._state.pullRequests.findIndex(
      (candidate) => candidate.url === pullRequest.url
    );
    if (index < 0) return;
    const pullRequests = [...this._state.pullRequests];
    pullRequests[index] = pullRequest;
    this._state = { kind: 'associated', pullRequests, observedAt: this.clock.now() };
  }
}
