// oxlint-disable-next-line typescript/no-explicit-any
type HookSchema = Record<string, (...args: any[]) => void | Promise<void>>;

export interface Hookable<T extends HookSchema> {
  on<K extends keyof T>(name: K, handler: T[K]): () => void;
}

export class HookCore<T extends HookSchema> implements Hookable<T> {
  private readonly hooks = new Map<keyof T, Set<T[keyof T]>>();

  constructor(private readonly onError: (name: keyof T, error: unknown) => void) {}

  on<K extends keyof T>(name: K, handler: T[K]): () => void {
    if (!this.hooks.has(name)) this.hooks.set(name, new Set());
    this.hooks.get(name)!.add(handler);
    return () => this.hooks.get(name)?.delete(handler);
  }

  async callHook<K extends keyof T>(name: K, ...args: Parameters<T[K]>): Promise<void> {
    for (const handler of this.hooks.get(name) ?? []) {
      await (handler as (...args: unknown[]) => unknown)(...args);
    }
  }

  callHookSync<K extends keyof T>(name: K, ...args: Parameters<T[K]>): void {
    for (const handler of this.hooks.get(name) ?? []) {
      const result = (handler as (...args: unknown[]) => unknown)(...args);
      if (result instanceof Promise) {
        throw new TypeError(`Hook "${String(name)}" returned a Promise in a sync context`);
      }
    }
  }

  callHookBackground<K extends keyof T>(name: K, ...args: Parameters<T[K]>): void {
    for (const handler of this.hooks.get(name) ?? []) {
      Promise.resolve((handler as (...args: unknown[]) => unknown)(...args)).catch((error) =>
        this.onError(name, { error: String(error) })
      );
    }
  }
}
