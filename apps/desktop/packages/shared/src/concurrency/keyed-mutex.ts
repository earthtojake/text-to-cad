export class KeyedMutex {
  private readonly locks = new Map<string, Promise<unknown>>();

  /**
   * Runs `fn` exclusively for `key`: concurrent calls on the same key are serialized
   * (each waits for the previous to finish before starting). Concurrent calls on
   * different keys run in parallel. A rejected `fn` does not block subsequent calls on
   * the same key.
   */
  async runExclusive<T>(key: string, fn: () => Promise<T>): Promise<T> {
    const previous = this.locks.get(key) ?? Promise.resolve();

    let release: () => void = () => {};
    const current = new Promise<void>((resolve) => {
      release = resolve;
    });
    const chained = previous.catch(() => {}).then(() => current);
    this.locks.set(key, chained);

    await previous.catch(() => {});
    try {
      return await fn();
    } finally {
      release();
      if (this.locks.get(key) === chained) {
        this.locks.delete(key);
      }
    }
  }
}
