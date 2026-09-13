import { computed, observable, type IComputedValue, type IObservableValue } from 'mobx';
import type { CommandDef, CommandInput, CommandOutput } from '@core/primitives/commands/api';
import type { JsonObject } from '@core/primitives/json/api';
import {
  enabled,
  viewScopeDefFor,
  type BoundCommand,
  type CommandBinding,
  type CommandSource,
  type ViewScopeDefinition,
  type ViewScopeHandle,
  type ViewScopeImpl,
  type ViewScopeRef,
} from '@core/primitives/view-scopes/api';
import { assertImplHasAllCommands } from './implementation-validation';

export type KeybindingHit =
  | { readonly kind: 'none' }
  | { readonly kind: 'consumed'; readonly commandId: string }
  | { readonly kind: 'winner'; readonly command: BoundCommand };

const noHit: KeybindingHit = Object.freeze({ kind: 'none' });

type BindingFactory = (params: JsonObject) => CommandBinding;

interface CaptureActivation {
  readonly generation: number;
  readonly instance: ViewScopeInstance;
  readonly focusActive: ViewScopeInstance | undefined;
}

function getBindingFactory(implementation: unknown, commandId: string): BindingFactory | undefined {
  if (implementation === null || typeof implementation !== 'object') return undefined;
  const candidate = (implementation as Readonly<Record<string, unknown>>)[commandId];
  return typeof candidate === 'function' ? (candidate as BindingFactory) : undefined;
}

class ScopeHandle implements ViewScopeHandle {
  readonly ref: ViewScopeRef;
  readonly def: ViewScopeDefinition;
  private readonly implementation: unknown;
  private readonly boundCommands = new Map<string, BoundCommand>();

  constructor(ref: ViewScopeRef, implementation: unknown) {
    this.ref = ref;
    this.def = viewScopeDefFor(ref);
    this.implementation = implementation;
  }

  getCommand<TCommand extends CommandDef>(command: TCommand): BoundCommand<TCommand> | undefined {
    const declared = this.def.commands.find((candidate) => candidate === command);
    if (!declared) return undefined;

    const cached = this.boundCommands.get(command.id);
    if (cached) return cached as BoundCommand<TCommand>;

    const factory = getBindingFactory(this.implementation, command.id);
    if (!factory) return undefined;
    const binding = factory(this.ref.params) as CommandBinding<TCommand>;
    const bound = Object.freeze({
      def: command,
      get availability() {
        return binding.availability?.() ?? enabled;
      },
      get presentation() {
        return binding.presentation?.();
      },
      execute(input: CommandInput<TCommand>, source: CommandSource = 'programmatic') {
        const parsed = command.input.parse(input) as CommandOutput<TCommand>;
        return binding.execute(parsed, source);
      },
    }) satisfies BoundCommand<TCommand>;
    this.boundCommands.set(command.id, bound);
    return bound;
  }
}

export interface InstantiateViewScopeOptions<TDef extends ViewScopeDefinition> {
  readonly parent?: ViewScopeInstance;
  readonly impl: ViewScopeImpl<TDef>;
}

export class ViewScopeInstance extends ScopeHandle {
  readonly id: string;
  readonly parent: ViewScopeInstance | undefined;
  readonly children = new Set<ViewScopeInstance>();
  readonly attachRef: (element: HTMLElement | null) => void;
  readonly attachFocusDelegate: (element: HTMLElement | null) => void;
  private readonly owner: ViewScopes;
  private attachedElement: HTMLElement | undefined;
  private focusDelegate: HTMLElement | undefined;
  private focusDelegateAction: (() => void) | undefined;
  private disposed = false;

  constructor(
    owner: ViewScopes,
    id: string,
    ref: ViewScopeRef,
    implementation: unknown,
    parent?: ViewScopeInstance
  ) {
    super(ref, implementation);
    this.owner = owner;
    this.id = id;
    this.parent = parent;
    this.attachRef = (element) => {
      if (this.attachedElement === element) return;
      this.attachedElement?.removeAttribute('data-view-scope');
      this.attachedElement = element ?? undefined;
      this.attachedElement?.setAttribute('data-view-scope', this.id);
      if (!element) this.owner.handleElementDetached(this);
    };
    this.attachFocusDelegate = (element) => {
      this.focusDelegate = element ?? undefined;
    };
  }

  get isDisposed(): boolean {
    return this.disposed;
  }

  focus(): boolean {
    if (this.disposed) return false;
    if (this.focusDelegateAction) {
      this.focusDelegateAction();
      return true;
    }
    const target =
      this.focusDelegate?.isConnected === true ? this.focusDelegate : this.attachedElement;
    if (!target?.isConnected) return false;
    target.focus({ preventScroll: true });
    return true;
  }

  setFocusDelegate(delegate: (() => void) | undefined): void {
    this.focusDelegateAction = delegate;
  }

  dispose(): void {
    if (this.disposed) return;
    this.disposed = true;
    for (const child of [...this.children]) {
      child.dispose();
    }
    this.setFocusDelegate(undefined);
    this.attachFocusDelegate(null);
    this.attachRef(null);
    this.owner.remove(this);
  }
}

export class ViewScopes {
  private nextId = 1;
  private nextCaptureGeneration = 1;
  private readonly instancesById = new Map<string, ViewScopeInstance>();
  private readonly logicalActive: IObservableValue<ViewScopeInstance | undefined>;
  private readonly focusActive: IObservableValue<ViewScopeInstance | undefined>;
  private readonly captureLayers: IObservableValue<readonly CaptureActivation[]>;
  private readonly activePathValue: IComputedValue<readonly ViewScopeHandle[]>;
  private readonly document: Document | undefined;

  constructor(document: Document | undefined = globalThis.document) {
    this.document = document;
    this.logicalActive = observable.box(undefined, { deep: false });
    this.focusActive = observable.box(undefined, { deep: false });
    this.captureLayers = observable.box(Object.freeze([]), { deep: false });
    this.activePathValue = computed(() => this.computeInstancePath(this.activeScopeInstance()));
    this.document?.addEventListener('focusin', this.handleFocusIn);
  }

  get activePath(): readonly ViewScopeHandle[] {
    return this.activePathValue.get();
  }

  isWithinActivePath(instance: ViewScopeInstance): boolean {
    return this.activePath.includes(instance);
  }

  instantiate<TDef extends ViewScopeDefinition = ViewScopeDefinition>(
    ref: ViewScopeRef,
    options: InstantiateViewScopeOptions<TDef>
  ): ViewScopeInstance {
    const definition = viewScopeDefFor(ref);
    if (import.meta.env.DEV) {
      assertImplHasAllCommands(definition, options.impl);
    }
    if (options.parent?.isDisposed) {
      throw new Error(`Cannot attach ${definition.id} to a disposed parent scope`);
    }

    const instance = new ViewScopeInstance(
      this,
      `view-scope-${this.nextId++}`,
      ref,
      options.impl,
      options.parent
    );
    options.parent?.children.add(instance);
    this.instancesById.set(instance.id, instance);
    return instance;
  }

  activate(instance: ViewScopeInstance | undefined): void {
    if (instance?.isDisposed) {
      throw new Error('Cannot activate a disposed view scope');
    }
    if (instance && instance.def.activation !== 'logical') {
      throw new Error(`View scope ${instance.def.id} does not use logical activation`);
    }
    const focused = this.focusActive.get();
    if (instance && focused && !this.isDescendantOf(focused, instance)) {
      this.focusActive.set(undefined);
    }
    this.logicalActive.set(instance);
  }

  /**
   * Activates a capture without replacing the logical or focused scope beneath it.
   * Reactivation is idempotent and moves the capture to the top. The returned disposer is
   * generation-bound, so stale owners cannot remove a newer activation.
   */
  activateCapture(instance: ViewScopeInstance): () => void {
    if (instance.isDisposed) {
      throw new Error('Cannot activate a disposed view scope as a capture');
    }
    if (!instance.def.traits.has('capturing')) {
      throw new Error(`View scope ${instance.def.id} is not capturing`);
    }
    const stack = this.captureLayers.get();
    const existing = stack.find((activation) => activation.instance === instance);
    const activation = Object.freeze({
      generation: this.nextCaptureGeneration++,
      instance,
      focusActive: existing?.focusActive,
    });
    this.captureLayers.set(
      Object.freeze([...stack.filter((candidate) => candidate.instance !== instance), activation])
    );

    return () => this.removeCaptureActivation(activation);
  }

  getActiveCommand<TCommand extends CommandDef>(
    command: TCommand,
    options: { readonly belowActiveCapture?: boolean } = {}
  ): BoundCommand<TCommand> | undefined {
    const activeCapture = this.topCaptureActivation();
    const path =
      options.belowActiveCapture && activeCapture
        ? this.computePathBelowCapture(activeCapture)
        : this.activePath;
    for (const handle of path) {
      const bound = handle.getCommand(command);
      if (bound) return bound;
      if (handle.def.traits.has('capturing')) return undefined;
    }
    return undefined;
  }

  resolveKeybinding(candidates: ReadonlySet<string>): KeybindingHit {
    return this.walkActivePath((handle) => {
      const declared = handle.def.commands.filter((command) => candidates.has(command.id));
      if (import.meta.env.DEV && declared.length > 1) {
        console.warn(
          `Multiple keybindings matched in view scope ${handle.def.id}; using declaration order: ${declared
            .map((command) => command.id)
            .join(', ')}`
        );
      }
      return declared;
    });
  }

  dispose(): void {
    this.document?.removeEventListener('focusin', this.handleFocusIn);
    for (const instance of [...this.instancesById.values()]) {
      if (!instance.parent) instance.dispose();
    }
    this.logicalActive.set(undefined);
    this.focusActive.set(undefined);
    this.captureLayers.set(Object.freeze([]));
  }

  /** @internal Called by ViewScopeInstance.dispose(). */
  remove(instance: ViewScopeInstance): void {
    this.removeCaptureInstance(instance);
    instance.parent?.children.delete(instance);
    this.instancesById.delete(instance.id);
    if (this.logicalActive.get() === instance) {
      this.logicalActive.set(this.nearestLiveAncestor(instance.parent, 'logical'));
    }
    if (this.focusActive.get() === instance) {
      this.focusActive.set(this.nearestLiveAncestor(instance.parent, 'focus'));
    }
  }

  /** @internal Called when an instance's attached DOM root is removed. */
  handleElementDetached(instance: ViewScopeInstance): void {
    this.clearCaptureFocus(instance);
    this.removeCaptureInstance(instance);
    if (this.focusActive.get() === instance) {
      this.focusActive.set(this.nearestLiveAncestor(instance.parent, 'focus'));
    }
  }

  private walkActivePath(
    candidatesFor: (handle: ViewScopeHandle) => readonly CommandDef[]
  ): KeybindingHit {
    for (const handle of this.activePath) {
      for (const command of candidatesFor(handle)) {
        const bound = handle.getCommand(command);
        if (!bound || bound.availability.kind === 'hidden') continue;
        if (bound.availability.kind === 'disabled') {
          return Object.freeze({ kind: 'consumed', commandId: command.id });
        }
        return Object.freeze({ kind: 'winner', command: bound });
      }
      if (handle.def.traits.has('capturing')) return noHit;
    }
    return noHit;
  }

  private computePathBelowCapture(capture: CaptureActivation): readonly ViewScopeInstance[] {
    const stack = this.captureLayers.get();
    const index = stack.findIndex((candidate) => candidate.generation === capture.generation);
    for (let candidateIndex = index - 1; candidateIndex >= 0; candidateIndex -= 1) {
      const candidate = stack[candidateIndex];
      if (candidate && !candidate.instance.isDisposed) {
        return this.computeInstancePath(this.captureScopeInstance(candidate));
      }
    }
    return this.computeInstancePath(this.ambientScopeInstance());
  }

  private computeInstancePath(
    instance: ViewScopeInstance | undefined
  ): readonly ViewScopeInstance[] {
    const path: ViewScopeInstance[] = [];
    let current = instance;
    while (current) {
      path.push(current);
      current = current.parent;
    }
    return Object.freeze(path);
  }

  private nearestLiveAncestor(
    instance: ViewScopeInstance | undefined,
    activation?: ViewScopeDefinition['activation']
  ): ViewScopeInstance | undefined {
    let current = instance;
    while (
      current &&
      (current.isDisposed || (activation && current.def.activation !== activation))
    ) {
      current = current.parent;
    }
    return current;
  }

  private isDescendantOf(instance: ViewScopeInstance, ancestor: ViewScopeInstance): boolean {
    let current: ViewScopeInstance | undefined = instance;
    while (current) {
      if (current === ancestor) return true;
      current = current.parent;
    }
    return false;
  }

  private isWithinCapturingScope(instance: ViewScopeInstance): boolean {
    let current: ViewScopeInstance | undefined = instance;
    while (current) {
      if (current.def.traits.has('capturing')) return true;
      current = current.parent;
    }
    return false;
  }

  private removeCaptureInstance(instance: ViewScopeInstance): void {
    const activations = this.captureLayers
      .get()
      .filter((activation) => activation.instance === instance);
    for (const activation of activations) this.removeCaptureActivation(activation);
  }

  private removeCaptureActivation(activation: CaptureActivation): void {
    const current = this.captureLayers.get();
    if (!current.some((candidate) => candidate.generation === activation.generation)) return;

    const remaining = current.filter((candidate) => candidate.generation !== activation.generation);
    this.captureLayers.set(Object.freeze(remaining));
  }

  private clearCaptureFocus(instance: ViewScopeInstance): void {
    const stack = this.captureLayers.get();
    const index = stack.findIndex((activation) => activation.focusActive === instance);
    if (index < 0) return;

    const activation = stack[index];
    if (!activation) return;
    const ancestor = this.nearestLiveAncestor(instance.parent, 'focus');
    const focusActive =
      ancestor && this.isDescendantOf(ancestor, activation.instance) ? ancestor : undefined;
    this.replaceCaptureActivation(index, { ...activation, focusActive });
  }

  private replaceCaptureActivation(index: number, activation: CaptureActivation): void {
    const stack = [...this.captureLayers.get()];
    stack[index] = Object.freeze(activation);
    this.captureLayers.set(Object.freeze(stack));
  }

  private activeScopeInstance(): ViewScopeInstance | undefined {
    const capture = this.topCaptureActivation();
    return capture ? this.captureScopeInstance(capture) : this.ambientScopeInstance();
  }

  private ambientScopeInstance(): ViewScopeInstance | undefined {
    const current = this.nearestLiveAncestor(this.focusActive.get(), 'focus');
    return current ?? this.nearestLiveAncestor(this.logicalActive.get(), 'logical');
  }

  private captureScopeInstance(capture: CaptureActivation): ViewScopeInstance {
    const focused = this.nearestLiveAncestor(capture.focusActive, 'focus');
    return focused && this.isDescendantOf(focused, capture.instance) ? focused : capture.instance;
  }

  private topCaptureActivation(): CaptureActivation | undefined {
    const stack = this.captureLayers.get();
    for (let index = stack.length - 1; index >= 0; index -= 1) {
      const activation = stack[index];
      if (activation && !activation.instance.isDisposed) return activation;
    }
    return undefined;
  }

  private readonly handleFocusIn = (event: FocusEvent): void => {
    const target = event.target;
    const ElementConstructor = this.document?.defaultView?.Element;
    const element =
      ElementConstructor && target instanceof ElementConstructor
        ? target.closest<HTMLElement>('[data-view-scope]')
        : null;
    const id = element?.getAttribute('data-view-scope');
    const instance = id ? this.instancesById.get(id) : undefined;
    if (!instance) return;

    const stack = this.captureLayers.get();
    for (let index = stack.length - 1; index >= 0; index -= 1) {
      const activation = stack[index];
      if (activation && this.isDescendantOf(instance, activation.instance)) {
        const focusActive = this.nearestLiveAncestor(instance, 'focus');
        this.replaceCaptureActivation(index, { ...activation, focusActive });
        return;
      }
    }
    // Capturing scopes only participate through activateCapture(). An outgoing
    // dialog can still emit focus events during its close animation; those
    // must not replace the focus scope underneath it.
    if (this.isWithinCapturingScope(instance)) return;
    if (instance.def.activation === 'logical') {
      this.focusActive.set(undefined);
      return;
    }
    this.focusActive.set(instance);
  };
}

export const scopes = new ViewScopes();

export function focusScope(instance: ViewScopeInstance | undefined): boolean {
  return instance?.focus() ?? false;
}
