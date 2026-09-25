import { unavailablePromptContext } from "@hardcore/core/prompt";
import type { ViewerHost } from "@hardcore/ui/host";

/**
 * An explicit, effect-free `ViewerHost` for mounting the explorer's renderers
 * outside the app: no IPC, no clipboard, no navigation. Never a production
 * default: the app builds its own in `features/explorer/FileTab.tsx`.
 */
export function testViewerHost(overrides: Partial<ViewerHost> = {}): ViewerHost {
  return {
    files: { id: "fixture", rootName: "Fixture", stat: async () => { throw new Error("unused"); } },
    clipboard: { writeText: async () => {}, readText: async () => "", writeImage: async () => {} },
    promptContext: unavailablePromptContext,
    navigation: { openFile() {} },
    environment: { colorScheme: "dark" },
    ...overrides,
  };
}
