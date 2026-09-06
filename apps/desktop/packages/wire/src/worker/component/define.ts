import type { ContractDefinitions } from '../../api/define';
import { createWireComponentInstance, type CreateWireComponentInstanceOptions } from './instance';
import type { InternalWireComponentInstance } from './internal';
import { assertExactRequirementKeys } from './requirements';
import type {
  DefineWireComponentOptions,
  WireComponentDefinition,
  WireComponentRequirements,
} from './types';

export function defineWireComponent<
  const Id extends string,
  const Requirements extends WireComponentRequirements,
  Defs extends ContractDefinitions,
  Config,
>(
  definition: DefineWireComponentOptions<Id, Defs, Requirements, Config>
): WireComponentDefinition<Id, Defs, Requirements, Config> {
  return Object.freeze({
    id: definition.id,
    contract: definition.contract,
    requirements: definition.requirements,
    configSchema: definition.configSchema,
    create(options) {
      const config = definition.configSchema.parse(options.config);
      assertExactRequirementKeys(
        definition.id,
        definition.requirements,
        options.dependencies as Record<string, unknown>
      );
      const componentScope = options.scope.child(`component:${definition.id}`);

      try {
        return definition.create({
          scope: componentScope,
          dependencies: options.dependencies,
          config,
          logger: options.logger ?? componentScope.log,
          signal: componentScope.signal,
          instance: ({ scope, controller }) => {
            const instance = createInstance({
              contract: definition.contract,
              controller,
              scope,
            });
            return instance;
          },
        });
      } catch (error) {
        void componentScope.dispose(error);
        throw error;
      }
    },
  });
}

function createInstance<Defs extends ContractDefinitions>(
  options: CreateWireComponentInstanceOptions<Defs>
): InternalWireComponentInstance<Defs> {
  return createWireComponentInstance(options);
}
