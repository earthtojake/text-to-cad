import { eq } from 'drizzle-orm';
import {
  DEFAULT_PROMPT_LIBRARY,
  PROMPT_LIBRARY_SEED_VERSION,
  promptLibrarySchema,
  type PromptLibraryPrompt,
} from '@core/primitives/prompt-library/api';
import type { AppDb } from '@core/services/app-db/node/db';
import { appSettings } from '@core/services/app-db/node/schema';

export type PromptLibraryKV = {
  prompts: PromptLibraryPrompt[];
  seedVersion: number;
};

export type PromptLibraryKeyValueStore = {
  get<K extends keyof PromptLibraryKV>(key: K): Promise<PromptLibraryKV[K] | null>;
  set<K extends keyof PromptLibraryKV>(key: K, value: PromptLibraryKV[K]): Promise<void>;
};

export class PromptLibraryService {
  private seedPromise: Promise<void> | null = null;

  constructor(
    private readonly db: AppDb,
    private readonly keyValueStore: PromptLibraryKeyValueStore
  ) {}

  private async readPrompts(): Promise<PromptLibraryPrompt[]> {
    const prompts = await this.keyValueStore.get('prompts');
    const parsed = promptLibrarySchema.safeParse(prompts ?? []);
    return parsed.success ? parsed.data : [];
  }

  private async readLegacyAppSetting(key: string): Promise<unknown | null> {
    const rows = await this.db
      .select({ value: appSettings.value })
      .from(appSettings)
      .where(eq(appSettings.key, key))
      .limit(1);
    const raw = rows[0]?.value;
    if (!raw) return null;

    try {
      return JSON.parse(raw) as unknown;
    } catch {
      return null;
    }
  }

  private async deleteLegacyPromptSettings(): Promise<void> {
    await this.db.delete(appSettings).where(eq(appSettings.key, 'promptLibrary'));
    await this.db.delete(appSettings).where(eq(appSettings.key, 'promptLibrarySeedVersion'));
    await this.db.delete(appSettings).where(eq(appSettings.key, 'reviewPrompt'));
  }

  private async seedIfNeeded(): Promise<void> {
    if (this.seedPromise) return this.seedPromise;

    this.seedPromise = (async () => {
      const seedVersion = await this.keyValueStore.get('seedVersion');
      if ((seedVersion ?? 0) >= PROMPT_LIBRARY_SEED_VERSION) {
        await this.deleteLegacyPromptSettings();
        return;
      }

      const existingPrompts = await this.readPrompts();
      const legacyPromptLibrary = promptLibrarySchema.safeParse(
        await this.readLegacyAppSetting('promptLibrary')
      );
      const legacyReviewPrompt = await this.readLegacyAppSetting('reviewPrompt');
      const prompts = [...existingPrompts];
      if (legacyPromptLibrary.success) {
        for (const legacyPrompt of legacyPromptLibrary.data) {
          if (!prompts.some((prompt) => prompt.id === legacyPrompt.id)) {
            prompts.push(legacyPrompt);
          }
        }
      }
      const defaultPrompts = DEFAULT_PROMPT_LIBRARY.map((prompt) =>
        prompt.id === 'review-prompt' && typeof legacyReviewPrompt === 'string'
          ? { ...prompt, prompt: legacyReviewPrompt }
          : prompt
      );
      const missingSeedPrompts = defaultPrompts.filter(
        (seedPrompt) => !prompts.some((prompt) => prompt.id === seedPrompt.id)
      );
      const nextPrompts = [...missingSeedPrompts, ...prompts];

      if (nextPrompts.length > 0) {
        await this.keyValueStore.set('prompts', nextPrompts);
      }
      await this.keyValueStore.set('seedVersion', PROMPT_LIBRARY_SEED_VERSION);
      await this.deleteLegacyPromptSettings();
    })().finally(() => {
      this.seedPromise = null;
    });

    await this.seedPromise;
  }

  async initialize(): Promise<void> {
    await this.seedIfNeeded();
  }

  async getPrompts(): Promise<PromptLibraryPrompt[]> {
    await this.seedIfNeeded();
    return this.readPrompts();
  }

  async updatePrompts(prompts: PromptLibraryPrompt[]): Promise<void> {
    const validated = promptLibrarySchema.parse(prompts);
    await this.keyValueStore.set('prompts', validated);
  }

  async upsertReviewPrompt(prompt: string): Promise<void> {
    const trimmedPrompt = prompt.trim();
    if (!trimmedPrompt) return;

    await this.seedIfNeeded();
    const prompts = await this.readPrompts();
    const reviewPrompt = {
      id: 'review-prompt',
      title: 'Review prompt',
      prompt: trimmedPrompt,
    };
    const exists = prompts.some((item) => item.id === reviewPrompt.id);
    const nextPrompts = exists
      ? prompts.map((item) => (item.id === reviewPrompt.id ? reviewPrompt : item))
      : [reviewPrompt, ...prompts];

    await this.keyValueStore.set('prompts', nextPrompts);
  }
}

export function createPromptLibraryService(options: {
  db: AppDb;
  keyValueStore: PromptLibraryKeyValueStore;
}): PromptLibraryService {
  return new PromptLibraryService(options.db, options.keyValueStore);
}
