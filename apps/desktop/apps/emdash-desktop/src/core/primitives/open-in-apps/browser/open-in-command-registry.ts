export interface OpenInCommandTarget {
  trigger(): void;
}

class OpenInCommandRegistry {
  private current: OpenInCommandTarget | undefined;

  register(target: OpenInCommandTarget): () => void {
    this.current = target;
    return () => {
      if (this.current === target) this.current = undefined;
    };
  }

  get(): OpenInCommandTarget | undefined {
    return this.current;
  }
}

export const openInCommandRegistry = new OpenInCommandRegistry();
