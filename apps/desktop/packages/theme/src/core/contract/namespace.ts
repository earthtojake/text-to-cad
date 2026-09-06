/**
 * namespace.ts — Single source of truth for the @emdash/ui CSS custom-property namespace.
 *
 * Every CSS custom property emitted by @emdash/ui is prefixed with `--em-` so the
 * library can coexist with a host app's own unprefixed vars without collision.
 *
 * Components and styles keep referencing tokens through VE typed accessors
 * (vars.background, tokenVars.radiusMd); the prefix is applied transparently
 * here, under the hood in the contract name functions and codegen key builders.
 *
 * Usage:
 *   import { nsName, nsVar } from './namespace';
 *   nsName('background')      // '--em-background'
 *   nsVar('background')       // 'var(--em-background)'
 *   nsName('neutral-11')      // '--em-neutral-11'
 *   nsVar('neutral-11')       // 'var(--em-neutral-11)'
 */

export const TOKEN_NAMESPACE = 'em';

/**
 * Returns the CSS custom property name with the namespace prefix applied.
 * e.g. nsName('background') → '--em-background'
 *
 * When TOKEN_NAMESPACE is empty, returns '--<name>' (prefix-free mode for tests).
 */
export function nsName(name: string): `--${string}` {
  return TOKEN_NAMESPACE ? `--${TOKEN_NAMESPACE}-${name}` : `--${name}`;
}

/**
 * Returns a CSS var() reference to the namespaced custom property.
 * e.g. nsVar('background') → 'var(--em-background)'
 *
 * Typed as `var(--${string})` so it matches Vanilla Extract's CSSVarFunction and
 * is assignable to any style property (including ones like `fontWeight` whose
 * csstype definition rejects arbitrary strings).
 */
export function nsVar(name: string): `var(--${string})` {
  return `var(${nsName(name)})`;
}
