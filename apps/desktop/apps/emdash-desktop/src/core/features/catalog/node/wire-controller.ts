import { err, ok, type Result } from '@emdash/shared';
import type { Contract, ContractImpl } from '@emdash/wire/rpc';
import type { catalogWireContract } from '@core/features/catalog/api';
import {
  catalogService,
  toCatalogServiceError,
  type CatalogServiceError,
} from '@core/features/catalog/node/catalog-service';

type CatalogDefinitions = typeof catalogWireContract extends Contract<infer Defs> ? Defs : never;
type CatalogWireImpl = ContractImpl<CatalogDefinitions>;

export function createCatalogWireController(): { impl: CatalogWireImpl; dispose(): Promise<void> } {
  return {
    impl: {
      getSkillsCatalog: () => wrap(() => catalogService.getSkillsCatalog()),
      refreshSkillsCatalog: () => wrap(() => catalogService.refreshSkillsCatalog()),
      searchSkillSh: ({ query }) => wrap(() => catalogService.searchSkillSh(query)),
      resolveSkillInstall: ({ skillId }) => wrap(() => catalogService.resolveSkillInstall(skillId)),
      getSkillContent: ({ skillId }) => wrap(() => catalogService.getSkillContent(skillId)),
      getMcpCatalog: (input) => wrap(() => catalogService.getMcpCatalog(input ?? undefined)),
    },
    async dispose() {},
  };
}

function wrap<T>(
  fn: () => Promise<T>
): Promise<Result<T, CatalogServiceError>> | Result<T, CatalogServiceError> {
  return fn().then(ok, (error) => err(toCatalogServiceError(error)));
}

export type CatalogWireController = ReturnType<typeof createCatalogWireController>;
