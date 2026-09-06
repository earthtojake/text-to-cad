import type { Contract, ContractDefinitions } from '../../api/define';
import type { WireComponentContractRequirement, WireComponentRequirements } from './types';

export function requireContract<Defs extends ContractDefinitions>(
  contract: Contract<Defs>
): WireComponentContractRequirement<Defs> {
  return { kind: 'contract', contract };
}

export function assertExactRequirementKeys(
  componentId: string,
  requirements: WireComponentRequirements,
  dependencies: Record<string, unknown>
): void {
  const required = new Set(Object.keys(requirements));
  const supplied = new Set(Object.keys(dependencies));

  const missing = [...required].filter((key) => !supplied.has(key));
  if (missing.length > 0) {
    throw new Error(
      `Wire component '${componentId}' is missing required dependencies: ${missing.join(', ')}`
    );
  }

  const extra = [...supplied].filter((key) => !required.has(key));
  if (extra.length > 0) {
    throw new Error(
      `Wire component '${componentId}' received unknown dependencies: ${extra.join(', ')}`
    );
  }
}
