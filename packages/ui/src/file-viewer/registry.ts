import { createElement } from "react";
import type { FileMetadata, FileRendererDefinition, PreparedDocument, RendererRegistration } from "./types.js";

/** Preserve the pairing between one renderer's loader and its prepared payload. */
export function defineFileRenderer<T>(definition: FileRendererDefinition<T>): RendererRegistration {
  return {
    id: definition.id,
    priority: definition.priority,
    matches: definition.matches,
    fallback: definition.fallback,
    panels: definition.panels,
    async prepare(context) {
      context.signal.throwIfAborted();
      let prepared: PreparedDocument<T> | undefined;
      let discarded = false;
      const dispose = () => { const owned = prepared; prepared = undefined; owned?.dispose?.(); };
      let onAbort = () => {};
      const aborted = new Promise<never>((_, reject) => {
        onAbort = () => { discarded = true; dispose(); reject(context.signal.reason); };
        context.signal.addEventListener("abort", onAbort, { once: true });
      });
      try {
        const [module, document] = await Promise.race([Promise.all([
          Promise.resolve().then(() => { context.signal.throwIfAborted(); return definition.load(); }),
          Promise.resolve().then(() => { context.signal.throwIfAborted(); return definition.prepare(context); }).then((result) => {
            if (discarded || context.signal.aborted) result.dispose?.();
            else prepared = result;
            return result;
          }),
        ]), aborted]);
        context.signal.throwIfAborted();
        const { default: Component } = module;
        return {
          Component: (props) => createElement(Component, { ...props, data: document.data }),
          text: document.text,
          dispose,
        };
      } catch (error) {
        discarded = true;
        dispose();
        throw error;
      } finally { context.signal.removeEventListener("abort", onAbort); }
    },
  };
}

export function validateRenderers(renderers: readonly RendererRegistration[]): void {
  const ids = new Set<string>();
  for (const renderer of renderers) {
    if (!renderer.id || ids.has(renderer.id)) throw new Error(`Duplicate or empty file renderer ID: "${renderer.id}".`);
    if (!Number.isFinite(renderer.priority)) throw new Error(`Renderer "${renderer.id}" has an invalid priority.`);
    ids.add(renderer.id);
  }
  if (renderers.filter((renderer) => renderer.fallback).length > 1) {
    throw new Error("Register at most one explicit fallback file renderer.");
  }
}

export function selectRenderer(renderers: readonly RendererRegistration[], file: FileMetadata): RendererRegistration {
  validateRenderers(renderers);
  const matches = renderers.filter((renderer) => !renderer.fallback && renderer.matches(file))
    .sort((left, right) => right.priority - left.priority);
  const first = matches[0];
  const second = matches[1];
  if (first && second && first.priority === second.priority) {
    throw new Error(`Ambiguous file renderers for "${file.path}": "${first.id}" and "${second.id}" both have priority ${first.priority}.`);
  }
  const selected = first ?? renderers.find((renderer) => renderer.fallback);
  if (!selected) throw new Error(`No registered renderer supports "${file.path}".`);
  return selected;
}
