import type { ViewScopeDefinition } from '@core/primitives/view-scopes/api';

export function assertImplHasAllCommands(
  definition: ViewScopeDefinition,
  implementation: unknown
): void {
  const record =
    implementation !== null && typeof implementation === 'object'
      ? (implementation as Readonly<Record<string, unknown>>)
      : {};
  const missing = definition.commands
    .filter((command) => typeof record[command.id] !== 'function')
    .map((command) => command.id);
  if (missing.length > 0) {
    throw new Error(
      `View scope implementation ${definition.id} is missing command bindings: ${missing.join(', ')}`
    );
  }
}
