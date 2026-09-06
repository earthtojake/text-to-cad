import type { Unsubscribe } from '@emdash/shared';
import { matchKeybindingPress } from 'tinykeys';
import {
  detectPlatformContext,
  type ChordKeyboardEventLike,
  type PlatformContext,
} from '@core/primitives/keybindings/api';
import {
  isTextInputFocusTarget,
  shouldIgnoreForOptions,
  type KeybindingFocusContext,
} from '@core/primitives/keybindings/browser';
import {
  keybindingService,
  type KeybindingService,
} from '@core/primitives/keybindings/browser/keybinding-service';
import { scopes, type KeybindingHit, type ViewScopes } from '@core/primitives/view-scopes/browser';

type SyntheticKeybindingEvent = Pick<ChordKeyboardEventLike, 'repeat' | 'isComposing'>;

const DEFAULT_SYNTHETIC_EVENT: SyntheticKeybindingEvent = Object.freeze({
  repeat: false,
  isComposing: false,
});

export class KeybindingDispatcher {
  private readonly service: KeybindingService;
  private readonly runtime: ViewScopes;
  private readonly context: PlatformContext;

  constructor(
    service: KeybindingService = keybindingService,
    runtime: ViewScopes = scopes,
    context: PlatformContext = detectPlatformContext()
  ) {
    this.service = service;
    this.runtime = runtime;
    this.context = context;
  }

  attach(target: Window): Unsubscribe {
    const onKeyDown = (event: KeyboardEvent) => {
      this.dispatch(event);
    };
    target.addEventListener('keydown', onKeyDown, { capture: true });
    return () => target.removeEventListener('keydown', onKeyDown, { capture: true });
  }

  dispatch(event: KeyboardEvent): KeybindingHit {
    const matched = new Set<string>();
    for (const entry of this.service.entries) {
      if (matchKeybindingPress(event, entry.press)) matched.add(entry.command.id);
    }

    const focus: KeybindingFocusContext = {
      textInputFocused:
        this.runtime.activePath.some((handle) => handle.def.traits.has('text-input')) ||
        isTextInputFocusTarget(event.target),
      editorFocused: this.runtime.activePath.some((handle) => handle.def.traits.has('editor')),
      terminalFocused: this.runtime.activePath.some((handle) => handle.def.traits.has('terminal')),
      browserFocused: false,
    };
    const candidates = this.gate(matched, event, focus);
    const hit = this.resolve(candidates);

    if (hit.kind === 'winner') {
      event.preventDefault();
      event.stopPropagation();
    } else if (hit.kind === 'consumed') {
      event.preventDefault();
    }
    return hit;
  }

  dispatchSynthetic(candidates: ReadonlySet<string>, focus: KeybindingFocusContext): KeybindingHit {
    return this.resolve(this.gate(candidates, DEFAULT_SYNTHETIC_EVENT, focus));
  }

  private gate(
    candidates: ReadonlySet<string>,
    event: SyntheticKeybindingEvent,
    focus: KeybindingFocusContext
  ): ReadonlySet<string> {
    const accepted = new Set<string>();
    for (const entry of this.service.entries) {
      if (
        candidates.has(entry.command.id) &&
        !shouldIgnoreForOptions(event as ChordKeyboardEventLike, entry.options, focus, this.context)
      ) {
        accepted.add(entry.command.id);
      }
    }
    return accepted;
  }

  private resolve(candidates: ReadonlySet<string>): KeybindingHit {
    const hit = this.runtime.resolveKeybinding(candidates);
    if (hit.kind === 'winner') {
      void hit.command.execute(undefined, 'keybinding');
    }
    return hit;
  }
}

export const keybindingDispatcher = new KeybindingDispatcher();
