import path from 'node:path';
import { fileURLToPath } from 'node:url';
import {
  DEFAULT_BOUNDARY_ALLOWLIST_PATH,
  DEFAULT_REPO_ROOT,
  isBoundaryFileAllowlisted,
  loadBoundaryAllowlists,
} from '../boundary-allowlists.js';

const MODULE_TYPES = new Set(['runtimes', 'services', 'primitives', 'features']);
const SHARED_INFRA_SERVICES = new Set(['app-db', 'operations']);
const ALIAS_PREFIXES = {
  '#runtimes/': 'runtimes',
  '#services/': 'services',
  '#primitives/': 'primitives',
  '@core/services/': 'services',
  '@core/primitives/': 'primitives',
  '@core/features/': 'features',
};
const CORE_PACKAGE_PREFIX = '@emdash/core/';

const currentDir = path.dirname(fileURLToPath(import.meta.url));
export const DEFAULT_CORE_SRC_ROOT = path.resolve(currentDir, '../../../packages/core/src');
export const DEFAULT_DESKTOP_CORE_SRC_ROOT = path.resolve(
  currentDir,
  '../../../apps/emdash-desktop/src/core'
);

export function normalizePath(value) {
  return value.replaceAll('\\', '/');
}

function normalizeAbsolute(value) {
  return normalizePath(path.resolve(normalizePath(value)));
}

export function classifyCorePath(filePath, coreSrcRoot = DEFAULT_CORE_SRC_ROOT) {
  const normalizedFile = normalizeAbsolute(filePath);
  const normalizedRoot = normalizeAbsolute(coreSrcRoot);
  if (normalizedFile !== normalizedRoot && !normalizedFile.startsWith(`${normalizedRoot}/`)) {
    return undefined;
  }

  const relative = normalizePath(path.relative(normalizedRoot, normalizedFile));
  const [type, moduleName, surface, nestedSurface] = relative.split('/');
  const platform =
    surface === 'api' && (nestedSurface === 'browser' || nestedSurface === 'node')
      ? nestedSurface
      : undefined;
  if (!MODULE_TYPES.has(type) || !moduleName) return undefined;
  return {
    type,
    moduleName,
    ...(surface ? { surface } : {}),
    ...(platform ? { platform } : {}),
  };
}

export function classifyImportSpecifier(specifier, fromFile, coreSrcRoot = DEFAULT_CORE_SRC_ROOT) {
  if (!specifier || typeof specifier !== 'string') return undefined;

  for (const [prefix, type] of Object.entries(ALIAS_PREFIXES)) {
    if (!specifier.startsWith(prefix)) continue;
    const rest = specifier.slice(prefix.length);
    const [moduleName, surface, nestedSurface] = rest.split('/');
    const platform =
      surface === 'api' && (nestedSurface === 'browser' || nestedSurface === 'node')
        ? nestedSurface
        : undefined;
    if (!moduleName) return undefined;
    return {
      type,
      moduleName,
      ...(surface ? { surface } : {}),
      ...(platform ? { platform } : {}),
    };
  }

  if (specifier.startsWith(CORE_PACKAGE_PREFIX)) {
    const rest = specifier.slice(CORE_PACKAGE_PREFIX.length);
    const [type, moduleName, surface, nestedSurface] = rest.split('/');
    const platform =
      surface === 'api' && (nestedSurface === 'browser' || nestedSurface === 'node')
        ? nestedSurface
        : undefined;
    if (!MODULE_TYPES.has(type) || !moduleName) return undefined;
    return {
      type,
      moduleName,
      ...(surface ? { surface } : {}),
      ...(platform ? { platform } : {}),
    };
  }

  if (specifier.startsWith('.')) {
    const target = path.resolve(path.dirname(fromFile), specifier);
    return classifyCorePath(target, coreSrcRoot);
  }

  return undefined;
}

export function isAllowedCoreModuleDependency(source, target) {
  if (!source || !target) return true;
  if (source.type === target.type && source.moduleName === target.moduleName) return true;
  if (target.type === 'services' && SHARED_INFRA_SERVICES.has(target.moduleName)) return true;

  if (source.type === 'services' && source.moduleName === 'runtime-broker') {
    return (
      (target.type === 'runtimes' && target.surface === 'api') ||
      (target.type === 'services' &&
        target.moduleName === 'host-dependencies' &&
        target.surface === 'api') ||
      target.type === 'primitives'
    );
  }

  // The session-lifecycle chassis types against the intent store and lifecycle
  // reporter ports (spec: conversation-lifecycle-chassis).
  if (source.type === 'services' && source.moduleName === 'session-lifecycle') {
    return (
      (target.type === 'services' &&
        (target.moduleName === 'session-intents' ||
          target.moduleName === 'conversation-reports')) ||
      target.type === 'primitives'
    );
  }

  if (source.type === 'runtimes') {
    return target.type === 'services' || target.type === 'primitives';
  }

  if (source.type === 'services') {
    return target.type === 'primitives';
  }

  if (source.type === 'features') {
    if (source.surface === 'api' && target.surface === 'api') {
      return true;
    }
    if (target.type === 'features') {
      return target.surface === 'api' || target.surface === 'contributions';
    }
    if (target.type === 'runtimes') {
      return target.surface === 'api';
    }
    if (
      (source.surface === 'node' || (source.surface === 'api' && source.platform === 'node')) &&
      target.type === 'services' &&
      (target.surface === 'api' || target.surface === 'node')
    ) {
      return true;
    }
    if (
      source.surface === 'browser' &&
      (target.type === 'primitives' ||
        target.surface === 'api' ||
        target.surface === 'contributions')
    ) {
      return true;
    }
    return target.type === 'primitives';
  }

  if (source.type === 'primitives') {
    return target.type === 'primitives';
  }

  return true;
}

export function dependencyMessage(source, target, specifier) {
  return `${source.type}/${source.moduleName} must not import ${target.type}/${
    target.moduleName
  } via '${specifier}'. Allowed Core module dependencies are: any module -> named shared-infra services (app-db/operations), runtime-broker -> runtime/host-dependency APIs and primitives, session-lifecycle -> session-intents/conversation-reports and primitives, runtimes -> services/primitives, services -> primitives, features -> other feature api/contributions surfaces, runtime APIs, and primitives, feature node surfaces -> service APIs/node surfaces, primitives -> primitives.`;
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

function checkImport(context, node, specifier, sourceModule, coreSrcRoot) {
  if (!specifier) return;
  const filename = getFilename(context);
  if (!filename) return;
  const targetModule = classifyImportSpecifier(specifier, filename, coreSrcRoot);
  if (!targetModule || isAllowedCoreModuleDependency(sourceModule, targetModule)) return;

  context.report({
    node,
    messageId: 'forbiddenDependency',
    data: {
      message: dependencyMessage(sourceModule, targetModule, specifier),
    },
  });
}

export const coreModuleBoundariesRule = {
  meta: {
    type: 'problem',
    messages: {
      forbiddenDependency: '{{message}}',
    },
    schema: [
      {
        type: 'object',
        properties: {
          coreSrcRoot: {
            type: 'string',
          },
          allowlistPath: {
            type: 'string',
          },
          repoRoot: {
            type: 'string',
          },
        },
        additionalProperties: false,
      },
    ],
  },
  create(context) {
    const options = getOptions(context);
    const filename = getFilename(context);
    const roots = options.coreSrcRoot
      ? [path.resolve(options.coreSrcRoot)]
      : [DEFAULT_CORE_SRC_ROOT, DEFAULT_DESKTOP_CORE_SRC_ROOT];
    const source = filename
      ? roots
          .map((coreSrcRoot) => ({
            coreSrcRoot,
            module: classifyCorePath(filename, coreSrcRoot),
          }))
          .find(({ module }) => module !== undefined)
      : undefined;
    if (!source?.module) return {};
    const { coreSrcRoot, module: sourceModule } = source;

    const allowlists = loadBoundaryAllowlists(
      options.allowlistPath ?? DEFAULT_BOUNDARY_ALLOWLIST_PATH
    );
    // A missing crossSlice key means "no exceptions": skip the allowlist
    // lookup entirely and report every cross-module violation as an error.
    const crossSliceAllowlist = allowlists.crossSlice;
    if (
      crossSliceAllowlist !== undefined &&
      isBoundaryFileAllowlisted(filename, crossSliceAllowlist, options.repoRoot ?? DEFAULT_REPO_ROOT)
    ) {
      return {};
    }

    return {
      ImportDeclaration(node) {
        checkImport(context, node, literalValue(node.source), sourceModule, coreSrcRoot);
      },
      ExportNamedDeclaration(node) {
        checkImport(context, node, literalValue(node.source), sourceModule, coreSrcRoot);
      },
      ExportAllDeclaration(node) {
        checkImport(context, node, literalValue(node.source), sourceModule, coreSrcRoot);
      },
      ImportExpression(node) {
        checkImport(context, node, importExpressionSource(node), sourceModule, coreSrcRoot);
      },
    };
  },
};
