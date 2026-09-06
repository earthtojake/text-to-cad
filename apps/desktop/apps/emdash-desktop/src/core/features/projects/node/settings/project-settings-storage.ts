import { eq, sql } from 'drizzle-orm';
import type { AppDb } from '@core/services/app-db/node/db';
import { projectSettings as projectSettingsTable } from '@core/services/app-db/node/schema';

export type StoredProjectSettings = {
  baseProjectSettingsJson: string;
  shareableProjectSettingsJson: string;
  legacyConfigMigratedAt: string | null;
};

export interface ProjectSettingsStorage {
  get(projectId: string): Promise<StoredProjectSettings | undefined>;
  insertIfMissing(projectId: string, settings: StoredProjectSettings): Promise<void>;
  update(projectId: string, settings: Partial<StoredProjectSettings>): Promise<void>;
}

export class ProjectSettingsRepository implements ProjectSettingsStorage {
  constructor(private readonly db: AppDb) {}

  async get(projectId: string): Promise<StoredProjectSettings | undefined> {
    const row = this.db
      .select()
      .from(projectSettingsTable)
      .where(eq(projectSettingsTable.projectId, projectId))
      .get();
    if (!row) return undefined;
    return {
      baseProjectSettingsJson: row.baseProjectSettingsJson,
      shareableProjectSettingsJson: row.shareableProjectSettingsJson,
      legacyConfigMigratedAt: row.legacyConfigMigratedAt,
    };
  }

  async insertIfMissing(projectId: string, settings: StoredProjectSettings): Promise<void> {
    await this.db
      .insert(projectSettingsTable)
      .values({
        projectId,
        baseProjectSettingsJson: settings.baseProjectSettingsJson,
        shareableProjectSettingsJson: settings.shareableProjectSettingsJson,
        legacyConfigMigratedAt: settings.legacyConfigMigratedAt,
        updatedAt: sql`CURRENT_TIMESTAMP`,
      })
      .onConflictDoNothing();
  }

  async update(projectId: string, settings: Partial<StoredProjectSettings>): Promise<void> {
    await this.db
      .update(projectSettingsTable)
      .set({
        ...settings,
        updatedAt: sql`CURRENT_TIMESTAMP`,
      })
      .where(eq(projectSettingsTable.projectId, projectId));
  }
}
