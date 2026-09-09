import { readFile, stat } from 'node:fs/promises';
import { builtinModules } from 'node:module';
import { join } from 'node:path';
import type { AdapterAsset } from './adapter-assets';
import { adapterAssetFileName } from './adapter-assets';

export const ADAPTER_BUNDLE_MAX_BYTES = 15 * 1024 * 1024;

const builtinModuleNames = new Set(builtinModules);

export type AdapterBundleValidationOptions = {
  readonly adapterDirectory: string;
  readonly assets: readonly AdapterAsset[];
  readonly maxBytes?: number;
};

export async function validateAdapterBundleAssets(
  options: AdapterBundleValidationOptions
): Promise<void> {
  const errors: string[] = [];
  const maxBytes = options.maxBytes ?? ADAPTER_BUNDLE_MAX_BYTES;

  for (const asset of options.assets) {
    const fileName = adapterAssetFileName(asset);
    const filePath = join(options.adapterDirectory, fileName);
    let source: string;
    let sizeBytes: number;

    try {
      const fileStat = await stat(filePath);
      if (!fileStat.isFile()) {
        errors.push(`${fileName} is not a file`);
        continue;
      }
      sizeBytes = fileStat.size;
      source = await readFile(filePath, 'utf8');
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      errors.push(`${fileName} is missing or unreadable: ${message}`);
      continue;
    }

    errors.push(...validateAdapterBundleSource({ fileName, source, sizeBytes, maxBytes }));
  }

  if (errors.length > 0) {
    throw new Error(`Adapter bundles failed validation:\n${errors.join('\n')}`);
  }
}

export function validateAdapterBundleSource(options: {
  readonly fileName: string;
  readonly source: string;
  readonly sizeBytes: number;
  readonly maxBytes?: number;
}): string[] {
  const errors: string[] = [];
  const maxBytes = options.maxBytes ?? ADAPTER_BUNDLE_MAX_BYTES;

  if (options.sizeBytes > maxBytes) {
    errors.push(
      `${options.fileName} is ${options.sizeBytes} bytes, above the ${maxBytes} byte limit`
    );
  }
  if (/['"][^'"\n]*\.node['"]/.test(options.source)) {
    errors.push(`${options.fileName} contains a native .node binding reference`);
  }

  for (const specifier of collectModuleSpecifiers(options.source)) {
    if (!isAllowedAdapterSpecifier(specifier)) {
      errors.push(`${options.fileName} contains unexpected external '${specifier}'`);
    }
  }

  return errors;
}

export function collectModuleSpecifiers(source: string): Set<string> {
  const specifiers = new Set<string>();

  for (const line of source.split('\n')) {
    const trimmed = line.trimStart();
    if (!trimmed.startsWith('import ') && !trimmed.startsWith('export ')) continue;
    const match = /\bfrom\s*['"]([^'"]+)['"]|^import\s*['"]([^'"]+)['"]/.exec(trimmed);
    const specifier = match?.[1] ?? match?.[2];
    if (specifier !== undefined) specifiers.add(specifier);
  }

  collectCallSpecifiers(source, 'require', specifiers);
  collectCallSpecifiers(source, '__require', specifiers);
  collectCallSpecifiers(source, 'import', specifiers);

  return specifiers;
}

function collectCallSpecifiers(source: string, callee: string, specifiers: Set<string>): void {
  let quote: '"' | "'" | '`' | undefined;
  let inLineComment = false;
  let inBlockComment = false;

  for (let index = 0; index < source.length; index += 1) {
    const char = source[index];
    const next = source[index + 1];

    if (inLineComment) {
      if (char === '\n') inLineComment = false;
      continue;
    }
    if (inBlockComment) {
      if (char === '*' && next === '/') {
        inBlockComment = false;
        index += 1;
      }
      continue;
    }
    if (quote !== undefined) {
      if (char === '\\') {
        index += 1;
        continue;
      }
      if (char === quote) quote = undefined;
      continue;
    }

    if (char === '/' && next === '/') {
      inLineComment = true;
      index += 1;
      continue;
    }
    if (char === '/' && next === '*') {
      inBlockComment = true;
      index += 1;
      continue;
    }
    if (char === '"' || char === "'" || char === '`') {
      quote = char;
      continue;
    }

    if (!source.startsWith(callee, index) || isIdentifierChar(source[index - 1])) continue;
    let cursor = index + callee.length;
    if (isIdentifierChar(source[cursor])) continue;
    while (/\s/.test(source[cursor] ?? '')) cursor += 1;
    if (source[cursor] !== '(') continue;
    cursor += 1;
    while (/\s/.test(source[cursor] ?? '')) cursor += 1;
    const literalQuote = source[cursor];
    if (literalQuote !== '"' && literalQuote !== "'") continue;
    cursor += 1;
    let specifier = '';
    for (; cursor < source.length; cursor += 1) {
      const literalChar = source[cursor];
      if (literalChar === '\\') {
        specifier += literalChar + (source[cursor + 1] ?? '');
        cursor += 1;
        continue;
      }
      if (literalChar === literalQuote) {
        specifiers.add(specifier);
        break;
      }
      specifier += literalChar;
    }
  }
}

function isIdentifierChar(char: string | undefined): boolean {
  return char !== undefined && /[$\w]/.test(char);
}

export function isAllowedAdapterSpecifier(specifier: string): boolean {
  if (specifier.startsWith('node:')) {
    return builtinModuleNames.has(specifier.slice('node:'.length));
  }
  return builtinModuleNames.has(specifier);
}
