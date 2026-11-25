import type { CadWorkspaceService } from '@cad/core/client';
import type { LiveRegistry } from '../host/liveRegistry.js';
import { createBoardRenderer } from '../renderers/board/index.js';
import { createDxfRenderer } from '../renderers/dxf/index.js';
import { createGlbRenderer } from '../renderers/glb/index.js';
import { createMeshRenderer } from '../renderers/mesh/index.js';
import { createRobotRenderer } from '../renderers/robot/index.js';
import { createSchematicRenderer } from '../renderers/schematic/index.js';
import type { CadPreferenceSource } from '../renderers/workspace/index.js';
import { createModelRenderer } from '../renderers/xbf/index.js';

/**
 * The CAD renderers over one client, reading the tab's preferences, bound to one live registry. A STEP
 * is drawn as an `.xbf` is, from what the engine serves of it (`renderers/xbf`).
 */
export function cadRenderers(client: CadWorkspaceService, preferences: CadPreferenceSource, live: LiveRegistry['binding']) {
  return [
    createDxfRenderer({ client, preferences, live }),
    createBoardRenderer({ client, preferences, live }),
    createSchematicRenderer({ client, preferences, live }),
    createGlbRenderer({ client, preferences, live }),
    createMeshRenderer({ client, preferences, live }),
    createRobotRenderer({ client, preferences, live }),
    createModelRenderer({ client, preferences, live }),
  ];
}
