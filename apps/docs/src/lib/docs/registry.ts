/**
 * The document types and the integrations, as the library's registry says them (`cad.registry`).
 * `registry.generated.json` is that table (`python -m cad.registry --docs`), and
 * tests/python/packages/cad/test_registry.py fails when the two differ, so a page here never says
 * of a type or an integration anything the library does not.
 */
import generated from "./registry.generated.json";

export type RegistryOperation = {
  name: string;
  summary: string;
  integration: string | null;
  engine: boolean;
};

export type RegistryDocumentType = {
  id: string;
  title: string;
  summary: string;
  extensions: string[];
  mime: string;
  view: string;
  content: string[];
  operations: RegistryOperation[];
  decorator: boolean;
  reader: boolean;
  readerIntegration: string | null;
  edit: { integration: string; noun: string; hands: string; changes: string[] } | null;
  producers: { integration: string; accepts: string; provides: string[] }[];
};

export type RegistryIntegration = {
  name: string;
  summary: string;
  extra: string | null;
  process: string;
  operations: RegistryOperation[];
  files: string[];
  modules: string[];
  distributions: string[];
  commands: string[];
  holds: string;
  downloadMb: number;
  alongside: string[];
  python: string | null;
  platforms: string[];
  program: { name: string; minimum: string; override: string } | null;
};

export const registry = generated as {
  operations: string[];
  integrationOperations: string[];
  views: string[];
  documentTypes: RegistryDocumentType[];
  integrations: RegistryIntegration[];
};

export const documentType = (id: string) => registry.documentTypes.find((entry) => entry.id === id);
export const integration = (name: string) => registry.integrations.find((entry) => entry.name === name);

// How each view is shown, in the registry's own words (`VIEWS`).
export const viewSummaries: Record<string, string> = {
  document: "exact geometry (a B-rep scene the engine serves)",
  mesh: "a triangle mesh",
  drawing: "a 2D drawing",
  robot: "a robot description",
  plot: "a plot of its layers or sheets",
};

/** Where an integration is used: the types whose operations, readers, producers or edits need it. */
export function usesOf(name: string) {
  return registry.documentTypes.flatMap((entry) => {
    const uses = [
      ...entry.operations.filter((operation) => operation.integration === name).map((operation) => operation.name),
      ...(entry.readerIntegration === name ? ["read"] : []),
      ...(entry.edit?.integration === name ? ["edit"] : []),
      ...(entry.producers.some((producer) => producer.integration === name) ? ["written by it"] : []),
    ];
    return uses.length ? [{ type: entry, uses }] : [];
  });
}
