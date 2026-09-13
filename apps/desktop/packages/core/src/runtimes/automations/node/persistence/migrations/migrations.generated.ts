// AUTO-GENERATED — do not edit. Re-run the bundle-drizzle-migrations script.
import type { BundledMigration } from '#primitives/sqlite-store/api';

export const migrations: readonly BundledMigration[] = [
  {
    idx: 0,
    tag: '0000_breezy_azazel',
    when: 1784245600964,
    hash: '38276740b1984ad445572d4ad37f02d03c570ef77a6bcb3d90d5af717cfa814c',
    sql: 'CREATE TABLE `automation_deployments` (\n\t`automation_id` text PRIMARY KEY NOT NULL,\n\t`enabled` integer NOT NULL,\n\t`payload` text NOT NULL,\n\t`deployed_at` integer NOT NULL\n);\n--> statement-breakpoint\nCREATE TABLE `automation_journal` (\n\t`singleton` integer PRIMARY KEY NOT NULL,\n\t`next_seq` integer NOT NULL,\n\tCONSTRAINT "automation_journal_singleton_check" CHECK("automation_journal"."singleton" = 1)\n);\n--> statement-breakpoint\nCREATE TABLE `automation_runs` (\n\t`id` text PRIMARY KEY NOT NULL,\n\t`seq` integer NOT NULL,\n\t`automation_id` text NOT NULL,\n\t`status` text NOT NULL,\n\t`scheduled_at` integer,\n\t`deadline_at` integer,\n\t`payload` text NOT NULL\n);\n--> statement-breakpoint\nCREATE UNIQUE INDEX `automation_runs_seq_idx` ON `automation_runs` (`seq`);--> statement-breakpoint\nCREATE UNIQUE INDEX `automation_runs_one_scheduled_idx` ON `automation_runs` (`automation_id`) WHERE "automation_runs"."status" = \'scheduled\';',
  },
  {
    idx: 1,
    tag: '0001_seed_journal',
    when: 1784245621250,
    hash: 'c5dab2ee69b2efa1d871350148d801de9c68edcc481618da47022957b66f3b77',
    sql: 'INSERT INTO automation_journal (singleton, next_seq) VALUES (1, 1);\n',
  },
];
