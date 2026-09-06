import { describe, expect, it } from 'vitest';
import { z } from 'zod';
import { workbenchLayout } from '@core/primitives/layouts/api';
import { defineView, defineViewCatalog } from '@core/primitives/views/api';
import {
  assertViewRuntimesComplete,
  defineViewRuntime,
  getViewRuntime,
  registerViewRuntime,
} from './runtime';

describe('view runtime registry', () => {
  it('registers a runtime against its definition', () => {
    const definition = defineView({
      id: 'runtime-test-registered',
      params: z.object({}),
      layout: workbenchLayout,
    });
    const contribution = defineViewRuntime(definition, {
      slots: {
        wrap: ({ children }) => children,
        main: () => null,
      },
    });

    registerViewRuntime(contribution);

    expect(getViewRuntime(definition.id)).toBe(contribution);
  });

  it('rejects duplicate runtime registrations', () => {
    const definition = defineView({
      id: 'runtime-test-duplicate',
      params: z.object({}),
      layout: workbenchLayout,
    });
    const contribution = defineViewRuntime(definition, {
      slots: {
        wrap: ({ children }) => children,
        main: () => null,
      },
    });

    registerViewRuntime(contribution);

    expect(() => registerViewRuntime(contribution)).toThrow(
      'Duplicate view runtime: runtime-test-duplicate'
    );
  });

  it('reports definitions without runtime contributions', () => {
    const registered = defineView({
      id: 'runtime-test-complete',
      params: z.object({}),
      layout: workbenchLayout,
    });
    const missing = defineView({
      id: 'runtime-test-missing',
      params: z.object({}),
      layout: workbenchLayout,
    });
    registerViewRuntime(
      defineViewRuntime(registered, {
        slots: {
          wrap: ({ children }) => children,
          main: () => null,
        },
      })
    );

    expect(() => assertViewRuntimesComplete(defineViewCatalog([registered, missing]))).toThrow(
      'Missing view runtimes: runtime-test-missing'
    );
  });
});
