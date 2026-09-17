import { unavailablePromptContext } from '@hardcore/core/prompt';
import type { ViewerHost } from '../types.js';
/** Explicit effect-free host for shared component tests. Never a production default. */
export function testHost(overrides: Partial<ViewerHost> = {}): ViewerHost {
  return {
    files: { id: 'fixture', rootName: 'Fixture', stat: async () => { throw new Error('unused'); } },
    clipboard: { writeText: async () => {}, readText: async () => '', writeImage: async () => {} },
    promptContext: unavailablePromptContext,
    navigation: { openFile() {} },
    environment: { colorScheme: 'dark' },
    ...overrides,
  };
}
