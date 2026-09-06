import type { Unsubscribe } from '@emdash/shared';
import { observable } from 'mobx';

export interface ConfirmAction {
  trigger(): void;
  isEnabled(): boolean;
}

export class ConfirmRegistry {
  private readonly actions = observable.array<ConfirmAction>([], { deep: false });

  register(action: ConfirmAction): Unsubscribe {
    this.actions.push(action);
    return () => {
      const index = this.actions.lastIndexOf(action);
      if (index !== -1) this.actions.splice(index, 1);
    };
  }

  get current(): ConfirmAction | undefined {
    return this.actions.at(-1);
  }
}

export const confirmRegistry = new ConfirmRegistry();
