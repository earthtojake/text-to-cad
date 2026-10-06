import { buildCadRefToken, parseCadRefSelector } from '../lib/cadRefs.js';

let operationSequence = 0;
const operationNamespace = globalThis.crypto?.randomUUID?.() ?? Math.random().toString(36).slice(2);
const object = value => Boolean(value && typeof value === 'object' && !Array.isArray(value));
function requireValue(condition, message) { if (!condition) throw new TypeError(`Invalid prompt context: ${message}`); }
function position(value) { return object(value) && Number.isSafeInteger(value.line) && value.line >= 0 && Number.isSafeInteger(value.character) && value.character >= 0; }

export function validatePromptReference(reference) {
  requireValue(object(reference) && object(reference.resource) && object(reference.target), 'reference requires a resource and target');
  const { resource, target } = reference;
  if (resource.kind === 'workspace-file') {
    // A file is named by its absolute path, `/`-separated (`/a/b.step`, `C:/a/b.step`).
    requireValue(typeof resource.path === 'string' && /^(?:[A-Za-z]:)?\//.test(resource.path) && !/[\\\0]/.test(resource.path)
      && resource.path.replace(/^(?:[A-Za-z]:)?\//, '').split('/').every(part => part && part !== '.' && part !== '..'), 'file paths must be normalized and absolute');
  } else {
    requireValue(resource.kind === 'url' && typeof resource.url === 'string', 'unknown resource kind');
    let url; try { url = new URL(resource.url); } catch { /* Report the contract error below. */ }
    requireValue(url && (url.protocol === 'http:' || url.protocol === 'https:'), 'URL references require HTTP(S)');
  }
  requireValue(resource.revision === undefined || typeof resource.revision === 'string', 'revision must be a string');
  requireValue(reference.label === undefined || typeof reference.label === 'string', 'label must be text');
  if (target.kind === 'text-range') {
    requireValue(position(target.start) && position(target.end), 'invalid text range');
    requireValue(target.end.line > target.start.line || (target.end.line === target.start.line && target.end.character >= target.start.character), 'range end precedes its start');
  } else if (target.kind === 'cad-selector') {
    // A selector names topology in a CAD file, whether the file is named by its path or, where a
    // host serves it at an address, by its URL (`https://host/b/<build>/STEP/a.step#f1`).
    requireValue(Array.isArray(target.selectors) && target.selectors.length > 0 && target.selectors.every(selector => {
      const parsed = typeof selector === 'string' && selector === selector.trim() ? parseCadRefSelector(selector) : null;
      return parsed && parsed.selectorType !== 'opaque';
    }), 'invalid CAD selector');
  } else requireValue(target.kind === 'whole-resource', 'unknown reference target');
  return reference;
}

/** Validate the envelope before any clipboard/draft effect. Attachment bytes are resolved by the host. */
export function validatePromptContext(context) {
  requireValue(object(context) && context.schemaVersion === 1, 'unsupported schema version');
  requireValue(typeof context.operationId === 'string' && context.operationId.length > 0, 'operation identity is required');
  requireValue(Array.isArray(context.parts) && context.parts.length > 0, 'at least one part is required');
  const ids = new Set();
  const references = new Set();
  for (const part of context.parts) {
    requireValue(object(part) && typeof part.id === 'string' && part.id.length > 0 && !ids.has(part.id), 'part ids must be nonempty and unique');
    ids.add(part.id);
    if (part.kind === 'text') requireValue(typeof part.text === 'string', 'text part must contain text');
    else if (part.kind === 'reference') { validatePromptReference(part.reference); references.add(part.id); }
    else {
      requireValue(part.kind === 'attachment', 'unknown part kind');
      requireValue(typeof part.name === 'string' && part.name.length > 0 && typeof part.mimeType === 'string' && /^[\w.+-]+\/[\w.+-]+$/.test(part.mimeType), 'attachment needs a name and MIME type');
      requireValue(part.content && (typeof part.content.arrayBuffer === 'function' || typeof part.content.then === 'function'), 'attachment must provide binary content');
      requireValue(part.about === undefined || (Array.isArray(part.about) && part.about.every(id => typeof id === 'string')), 'attachment relationships must name reference parts');
      requireValue(part.label === undefined || typeof part.label === 'string', 'attachment label must be text');
    }
  }
  for (const part of context.parts) if (part.kind === 'attachment') {
    requireValue((part.about ?? []).every(id => references.has(id)), 'attachment refers to an absent reference');
  }
  return context;
}

export function createPromptContext(parts, operationId = `${operationNamespace}:${++operationSequence}`) {
  validatePromptContext({ schemaVersion: 1, operationId, parts });
  const snapshot = parts.map(part => {
    if (part.kind === 'reference') {
      const target = part.reference.target;
      const frozenTarget = target.kind === 'cad-selector' ? { ...target, selectors: Object.freeze([...target.selectors]) }
        : target.kind === 'text-range' ? { ...target, start: Object.freeze({ ...target.start }), end: Object.freeze({ ...target.end }) } : { ...target };
      return Object.freeze({ ...part, reference: Object.freeze({ ...part.reference,
        resource: Object.freeze({ ...part.reference.resource }), target: Object.freeze(frozenTarget) }) });
    }
    return Object.freeze(part.kind === 'attachment' && part.about ? { ...part, about: Object.freeze([...part.about]) } : { ...part });
  });
  return Object.freeze({ schemaVersion: 1, operationId, parts: Object.freeze(snapshot) });
}
export function referencePart(reference, id = 'reference') { return { id, kind: 'reference', reference: validatePromptReference(reference) }; }
export function textPart(text, id = 'text') { return { id, kind: 'text', text }; }

/**
 * What a reference names inside its file, as a person reads it, one id a line: each CAD selector,
 * a text range's span (its label, if it has one), or a whole file's label.
 */
export function promptReferenceIds(reference) {
  const { target } = reference;
  if (target.kind === 'cad-selector') return target.selectors.map(String);
  if (target.kind === 'text-range') {
    const { start, end } = target;
    return [reference.label || `${start.line + 1}:${start.character + 1}–${end.line + 1}:${end.character + 1}`];
  }
  return reference.label ? [reference.label] : [];
}

/** Keep machine identity structured; these strings are the portable human/prompt representation. */
export function formatPromptReference(reference) {
  validatePromptReference(reference);
  // A file by its absolute path, a URL as it is.
  const path = reference.resource.kind === 'url' ? reference.resource.url : reference.resource.path;
  requireValue(path.length > 0, 'a reference names its file or URL');
  if (reference.target.kind === 'cad-selector') return buildCadRefToken({ cadPath: path, selectors: [...reference.target.selectors] });
  const quoted = /[\s#"\\]/.test(path) ? JSON.stringify(path) : path;
  if (reference.target.kind === 'text-range') {
    const { start, end } = reference.target;
    return `${quoted}:${start.line + 1}:${start.character + 1}-${end.line + 1}:${end.character + 1}`;
  }
  return quoted;
}
export function formatPromptContextText(context) {
  validatePromptContext(context);
  return context.parts.flatMap(part => part.kind === 'text' ? [part.text] : part.kind === 'reference' ? [formatPromptReference(part.reference)] : []).join('\n');
}

/**
 * A context as one message, the way a person would write it: what they said, then what it is
 * about — each whole file on a `File:` line, the selections in it under `References:`, one per
 * line — then each attachment that travels as a file, by its label and path (`attachmentPath`;
 * one sent beside the text is left out). One spelling, whether the message is sent, queued or copied.
 */
export function formatPromptMessage(context, { attachmentPath } = {}) {
  validatePromptContext(context);
  const said = context.parts.filter(part => part.kind === 'text').map(part => part.text.trim()).filter(Boolean);
  const files = [], references = [], attachments = [];
  for (const part of context.parts) {
    if (part.kind === 'reference') (part.reference.target.kind === 'whole-resource' ? files : references).push(formatPromptReference(part.reference));
    else if (part.kind === 'attachment') {
      const path = attachmentPath?.(part);
      if (path) attachments.push(`${part.label || 'Attachment'}: ${path}`);
    }
  }
  const about = [...files.map(file => `File: ${file}`), ...(references.length ? ['References:', ...references] : []), ...attachments];
  return [said.join('\n\n'), about.join('\n')].filter(Boolean).join('\n\n');
}

const failureMessage = error => error instanceof Error ? error.message : String(error);
/**
 * The bookkeeping every `PromptContextPort.deliver` shares. `deliver(operationId, start)` starts
 * one delivery per operation id — a repeated call for a bundle already on its way (or delivered)
 * gets that first operation's result — refuses a delivery while `maxPending` are in flight, and
 * remembers at most `maxRemembered` operations, evicting completed ones first. A failed or
 * cancelled operation is forgotten, so the same bundle can be tried again. `start` runs at once,
 * inside the caller's gesture; a throw or a rejection becomes a `failed` result.
 */
export function createPromptDeliveryLedger({ maxPending = 16, maxRemembered = 256, busyMessage = 'Wait for pending prompt deliveries before sending more.' } = {}) {
  const operations = new Map();
  const pending = new Set();
  return {
    deliver(operationId, start) {
      const previous = operations.get(operationId);
      if (previous) return previous;
      if (pending.size >= maxPending) return Promise.resolve({ status: 'failed', message: busyMessage });
      let operation;
      try { operation = Promise.resolve(start()); }
      catch (error) { operation = Promise.resolve({ status: 'failed', message: failureMessage(error) }); }
      operation = operation.catch(error => ({ status: 'failed', message: failureMessage(error) }));
      while (operations.size >= maxRemembered) {
        const completed = [...operations.keys()].find(id => !pending.has(id));
        if (!completed) break;
        operations.delete(completed);
      }
      operations.set(operationId, operation);
      pending.add(operationId);
      void operation.then(result => {
        pending.delete(operationId);
        if (result.status === 'failed' || result.status === 'cancelled') operations.delete(operationId);
      });
      return operation;
    },
  };
}

const unavailable = Object.freeze({ kind: 'unavailable', available: false, reason: 'Prompt delivery is unavailable in this host.' });
/** An explicit composition choice for a host with no prompt workflow; never discovers globals. */
export const unavailablePromptContext = Object.freeze({
  getSnapshot: () => unavailable,
  subscribe: () => () => {},
  deliver: async () => ({ status: 'failed', message: unavailable.reason }),
});
