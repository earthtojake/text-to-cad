// AUTO-GENERATED — do not edit. Re-run the bundle-drizzle-migrations script.
import type { BundledMigration } from '#primitives/sqlite-store/api';

export const migrations: readonly BundledMigration[] = [
  {
    idx: 0,
    tag: '0000_cuddly_exiles',
    when: 1785887497941,
    hash: 'eed928fa8488d639c9862719ce8249a04fdb03b0cd3367e0e5f0b375dcdd08d3',
    sql: 'CREATE TABLE `conversation_records` (\n\t`id` text PRIMARY KEY NOT NULL,\n\t`provider` text NOT NULL,\n\t`type` text NOT NULL,\n\t`cwd` text NOT NULL,\n\t`workspace_path` text NOT NULL,\n\t`created_at` integer NOT NULL,\n\t`title` text NOT NULL,\n\t`config` text NOT NULL,\n\t`provider_link` text NOT NULL,\n\t`last_session_activity_at` integer,\n\t`last_spawned_at` integer,\n\t`last_resume_outcome` text NOT NULL,\n\t`updated_at` integer NOT NULL\n);\n',
  },
];
