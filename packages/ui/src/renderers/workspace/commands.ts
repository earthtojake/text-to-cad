/**
 * Host requests every viewer renderer answers. A snapshot of the view goes to the
 * prompt; a request to select a reference is carried out by a renderer that has
 * references, and consumed and declined in words by one that has none.
 */
export interface ViewerCommands {
  captureRequest?: { key: string | number } | null;
  selectReference?: { selector: string; key?: string | number } | null;
}
export interface ViewerCommandSource {
  subscribe(listener: () => void): () => void;
  getSnapshot(): ViewerCommands;
  /** Remove only this admitted command; a later nonce must survive an old acknowledgement. */
  acknowledge?(kind: keyof ViewerCommands, key: string | number): void;
}
