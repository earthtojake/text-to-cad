import path from 'node:path';
import { fileURLToPath } from 'node:url';
import {
  DEFAULT_BOUNDARY_ALLOWLIST_PATH,
  DEFAULT_REPO_ROOT,
  isBoundaryFileAllowlisted,
  loadBoundaryAllowlists,
} from '../boundary-allowlists.js';

const currentDir = path.dirname(fileURLToPath(import.meta.url));

export const DEFAULT_DESKTOP_CORE_SRC_ROOT = path.resolve(
  currentDir,
  '../../../apps/emdash-desktop/src/core'
);
export const DEFAULT_MAIN_CORE_SRC_ROOT = path.resolve(
  currentDir,
  '../../../apps/emdash-desktop/src/main/core'
);

function normalizePath(value) {
  return path.resolve(value).replaceAll('\\', '/');
}

function isWithin(filePath, root) {
  const normalizedFile = normalizePath(filePath);
  const normalizedRoot = normalizePath(root);
  return normalizedFile === normalizedRoot || normalizedFile.startsWith(`${normalizedRoot}/`);
}

function getFilename(context) {
  return context.filename ?? context.getFilename?.() ?? context.physicalFilename ?? '';
}

function getOptions(context) {
  const [options] = context.options ?? [];
  return options && typeof options === 'object' ? options : {};
}

function literalValue(node) {
  const value = node?.value;
  return typeof value === 'string' ? value : undefined;
}

function importExpressionSource(node) {
  return literalValue(node.source) ?? literalValue(node.arguments?.[0]);
}

export function isCoreHostSpecifier(specifier) {
  return specifier?.startsWith('@main/') || specifier?.startsWith('@renderer/');
}

export function isMainCoreFeatureSpecifier(specifier) {
  return specifier?.startsWith('@core/features/');
}

function reportImport(context, node, specifier, boundary) {
  if (!specifier) return;
  if (boundary === 'coreToHost' && isCoreHostSpecifier(specifier)) {
    context.report({
      node,
      messageId: 'coreImportsHost',
      data: { specifier },
    });
  }
  if (boundary === 'mainCoreToFeatures' && isMainCoreFeatureSpecifier(specifier)) {
    context.report({
      node,
      messageId: 'mainCoreImportsFeature',
      data: { specifier },
    });
  }
}

export const coreHostBoundariesRule = {
  meta: {
    type: 'problem',
    messages: {
      coreImportsHost:
        "Core must not import host module '{{specifier}}'. Inject a capability or move the shared abstraction into core.",
      mainCoreImportsFeature:
        "Main domain logic must not import feature slice '{{specifier}}'. Move the domain into its slice or depend on a core API.",
    },
    schema: [
      {
        type: 'object',
        properties: {
          allowlistPath: { type: 'string' },
          repoRoot: { type: 'string' },
          coreSrcRoot: { type: 'string' },
          mainCoreSrcRoot: { type: 'string' },
        },
        additionalProperties: false,
      },
    ],
  },
  create(context) {
    const options = getOptions(context);
    const filename = getFilename(context);
    if (!filename) return {};

    const coreSrcRoot = options.coreSrcRoot ?? DEFAULT_DESKTOP_CORE_SRC_ROOT;
    const mainCoreSrcRoot = options.mainCoreSrcRoot ?? DEFAULT_MAIN_CORE_SRC_ROOT;
    const boundary = isWithin(filename, coreSrcRoot)
      ? 'coreToHost'
      : isWithin(filename, mainCoreSrcRoot)
        ? 'mainCoreToFeatures'
        : undefined;
    if (!boundary) return {};

    const allowlists = loadBoundaryAllowlists(
      options.allowlistPath ?? DEFAULT_BOUNDARY_ALLOWLIST_PATH
    );
    if (
      isBoundaryFileAllowlisted(
        filename,
        allowlists[boundary],
        options.repoRoot ?? DEFAULT_REPO_ROOT
      )
    ) {
      return {};
    }

    return {
      ImportDeclaration(node) {
        reportImport(context, node, literalValue(node.source), boundary);
      },
      ExportNamedDeclaration(node) {
        reportImport(context, node, literalValue(node.source), boundary);
      },
      ExportAllDeclaration(node) {
        reportImport(context, node, literalValue(node.source), boundary);
      },
      ImportExpression(node) {
        reportImport(context, node, importExpressionSource(node), boundary);
      },
    };
  },
};
