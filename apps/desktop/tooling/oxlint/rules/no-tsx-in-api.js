import path from 'node:path';
import { fileURLToPath } from 'node:url';
import {
  DEFAULT_API_SURFACE_ALLOWLIST_PATH,
  DEFAULT_REPO_ROOT,
  isBoundaryFileAllowlisted,
  loadBoundaryAllowlists,
} from '../boundary-allowlists.js';

const currentDir = path.dirname(fileURLToPath(import.meta.url));

export const DEFAULT_DESKTOP_CORE_SRC_ROOT = path.resolve(
  currentDir,
  '../../../apps/emdash-desktop/src/core'
);

function normalizePath(value) {
  return path.resolve(value).replaceAll('\\', '/');
}

function getFilename(context) {
  return context.filename ?? context.getFilename?.() ?? context.physicalFilename ?? '';
}

function getOptions(context) {
  const [options] = context.options ?? [];
  return options && typeof options === 'object' ? options : {};
}

/**
 * True when the file is a `.tsx` file under a feature api surface:
 * `<coreSrcRoot>/features/<slice>/api/**`.
 */
export function isTsxInApiFile(filename, coreSrcRoot = DEFAULT_DESKTOP_CORE_SRC_ROOT) {
  if (!filename || !filename.endsWith('.tsx')) return false;
  const normalizedFile = normalizePath(filename);
  const normalizedRoot = normalizePath(coreSrcRoot);
  if (!normalizedFile.startsWith(`${normalizedRoot}/features/`)) return false;
  const [sliceName, surface] = normalizedFile
    .slice(`${normalizedRoot}/features/`.length)
    .split('/');
  return Boolean(sliceName) && surface === 'api';
}

export const noTsxInApiRule = {
  meta: {
    type: 'problem',
    messages: {
      tsxInApi:
        'api surfaces hold contracts, types, clients, and store selectors; React components belong in browser/ and reach other slices through contributions.',
    },
    schema: [
      {
        type: 'object',
        properties: {
          coreSrcRoot: { type: 'string' },
          allowlistPath: { type: 'string' },
          repoRoot: { type: 'string' },
        },
        additionalProperties: false,
      },
    ],
  },
  create(context) {
    const options = getOptions(context);
    const filename = getFilename(context);
    if (!isTsxInApiFile(filename, options.coreSrcRoot ?? DEFAULT_DESKTOP_CORE_SRC_ROOT)) {
      return {};
    }

    const allowlists = loadBoundaryAllowlists(
      options.allowlistPath ?? DEFAULT_API_SURFACE_ALLOWLIST_PATH
    );
    if (
      isBoundaryFileAllowlisted(
        filename,
        allowlists.tsxInApi,
        options.repoRoot ?? DEFAULT_REPO_ROOT
      )
    ) {
      return {};
    }

    return {
      Program(node) {
        context.report({ node, messageId: 'tsxInApi' });
      },
    };
  },
};
