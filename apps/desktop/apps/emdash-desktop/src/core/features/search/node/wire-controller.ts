import { createController, type Controller } from '@emdash/wire/rpc';
import { searchContract } from '../api';
import type { SearchService } from './search-service';

export function createSearchWireController(service: SearchService): Controller {
  return createController(searchContract, {
    searchPaletteEntities: (input) => service.searchEntities(input),
    searchWorkspaceFiles: ({ workspaceId, query, limit }) =>
      service.searchFiles(workspaceId, query, limit),
    searchWorkspaceContent: {
      run: (input, context) => service.searchContent(input, context),
    },
  });
}
