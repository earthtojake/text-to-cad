// Type-resolution shim for the browser program (mapped via `paths` in
// tsconfig.browser.json). The real @types/jsdom references `node` types,
// which would drag all node ambient globals (process, Buffer, ...) into the
// browser program through the renderer/core tests that build a document with
// jsdom. Those tests only construct `new JSDOM(html, { url })` and read
// `.window`, so declare exactly that surface with DOM types instead.
export interface JSDOMOptions {
  url?: string;
}

export class JSDOM {
  constructor(html?: string, options?: JSDOMOptions);
  readonly window: Window & typeof globalThis;
}
