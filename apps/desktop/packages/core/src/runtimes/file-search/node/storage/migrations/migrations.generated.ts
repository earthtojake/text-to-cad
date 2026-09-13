// AUTO-GENERATED — do not edit. Re-run the bundle-drizzle-migrations script.
import type { BundledMigration } from '#primitives/sqlite-store/api';

export const migrations: readonly BundledMigration[] = [
  {
    idx: 0,
    tag: '0000_mute_albert_cleary',
    when: 1784591523951,
    hash: '7b422fe73de4a220059d1eec4d23e250068ad9ee73d4ca60c78b3ff72d190b77',
    sql: 'CREATE TABLE `path_entries` (\n\t`id` integer PRIMARY KEY AUTOINCREMENT NOT NULL,\n\t`root_id` integer NOT NULL,\n\t`generation` integer NOT NULL,\n\t`relative_path` text NOT NULL,\n\t`name` text NOT NULL,\n\t`kind` text NOT NULL,\n\tFOREIGN KEY (`root_id`) REFERENCES `registered_roots`(`id`) ON UPDATE no action ON DELETE cascade,\n\tCONSTRAINT "path_entries_generation_check" CHECK("path_entries"."generation" >= 1),\n\tCONSTRAINT "path_entries_relative_path_check" CHECK(length("path_entries"."relative_path") > 0),\n\tCONSTRAINT "path_entries_name_check" CHECK(length("path_entries"."name") > 0),\n\tCONSTRAINT "path_entries_kind_check" CHECK("path_entries"."kind" IN (\'file\', \'directory\'))\n);\n--> statement-breakpoint\nCREATE UNIQUE INDEX `path_entries_root_generation_path_idx` ON `path_entries` (`root_id`,`generation`,`relative_path`);--> statement-breakpoint\nCREATE TABLE `registered_roots` (\n\t`id` integer PRIMARY KEY AUTOINCREMENT NOT NULL,\n\t`root_key` text NOT NULL,\n\t`root_path` text NOT NULL,\n\t`current_generation` integer,\n\tCONSTRAINT "registered_roots_root_key_check" CHECK(length("registered_roots"."root_key") > 0),\n\tCONSTRAINT "registered_roots_root_path_check" CHECK(length("registered_roots"."root_path") > 0),\n\tCONSTRAINT "registered_roots_current_generation_check" CHECK("registered_roots"."current_generation" >= 1)\n);\n--> statement-breakpoint\nCREATE UNIQUE INDEX `registered_roots_root_key_idx` ON `registered_roots` (`root_key`);',
  },
];
