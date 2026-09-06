import type {
  FocusContext,
  FocusedRegion,
  FocusMainPanel,
  FocusTrigger,
  FocusView,
  TelemetryEventProperties,
} from '../api/telemetry';

interface FocusState {
  view: FocusView | null;
  mainPanel: FocusMainPanel | null;
  focusedRegion: FocusedRegion | null;
}

export interface FocusTransitionResult {
  previous: FocusState;
  changed: boolean;
}

type FocusChangedPayload = TelemetryEventProperties['focus_changed'];

type TransitionEmitter = (payload: FocusChangedPayload) => void;

export class FocusTracker {
  private state: FocusState = {
    view: null,
    mainPanel: null,
    focusedRegion: null,
  };

  private initialized = false;
  private transitionEmitter?: TransitionEmitter;

  initialize(initial: Partial<FocusState>): void {
    if (this.initialized) return;
    this.state = {
      ...this.state,
      ...initial,
    };
    this.initialized = true;
  }

  setTransitionEmitter(emitter: TransitionEmitter): void {
    this.transitionEmitter = emitter;
  }

  transition(partial: Partial<FocusState>, trigger: FocusTrigger): FocusTransitionResult | null {
    if (!this.initialized) {
      this.initialize(partial);
      return null;
    }

    const previous = { ...this.state };
    const changed = (Object.keys(partial) as Array<keyof FocusState>).some((key) => {
      const value = partial[key];
      if (value === undefined) return false;
      return this.state[key] !== value;
    });
    if (!changed) return null;

    this.transitionEmitter?.({
      view: previous.view,
      main_panel: previous.mainPanel,
      focused_region: previous.focusedRegion,
      trigger,
    });

    this.state = {
      ...this.state,
      ...partial,
    };

    return {
      previous,
      changed,
    };
  }

  getContext(): FocusContext {
    return {
      active_view: this.state.view,
      active_main_panel: this.state.mainPanel,
      focused_region: this.state.focusedRegion,
    };
  }
}

export const focusTracker = new FocusTracker();
