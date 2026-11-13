/**
 * The document types and the integrations, as the library's registry says them (`cad.registry`):
 * each type's operations, and what each integration brings. `registry.generated.json` is that table
 * (`python -m cad.registry --docs`), and tests/python/packages/cad/test_registry.py fails when the
 * two differ, so a page here never says of a type or an integration anything the library does not.
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
