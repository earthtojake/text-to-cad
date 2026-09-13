// AUTO-GENERATED — do not edit. Re-run the bundle-drizzle-migrations script.
import type { BundledMigration } from '#primitives/sqlite-store/api';

export const migrations: readonly BundledMigration[] = [
  {
    idx: 0,
    tag: '0000_thankful_white_tiger',
    when: 1785962601628,
    hash: '943970b0e5503eb7f89f038d1c551f47d0fe394999e2908ce1ac1f77a12b6a43',
    sql: 'CREATE TABLE `workspace_records` (\n\t`id` text PRIMARY KEY NOT NULL,\n\t`kind` text NOT NULL,\n\t`path` text NOT NULL,\n\t`parent_id` text,\n\t`origin` text NOT NULL,\n\t`git_admin_name` text,\n\t`observed_status` text NOT NULL,\n\t`creation` text,\n\t`last_create_outcome` text,\n\t`git` text,\n\t`last_activated_at` integer,\n\t`created_at` integer NOT NULL,\n\t`updated_at` integer NOT NULL,\n\t`last_observed_at` integer NOT NULL\n);\n--> statement-breakpoint\nCREATE UNIQUE INDEX `workspace_records_path_unique` ON `workspace_records` (`path`);',
  },
  {
    idx: 1,
    tag: '0001_tiny_moonstone',
    when: 1785976062469,
    hash: '57a9e2e208810b11fa60d39b6382e5b252c0a1c30dea11f4f26078de21b15f01',
    sql: 'ALTER TABLE `workspace_records` ADD `last_removal_attempt` text;--> statement-breakpoint\nALTER TABLE `workspace_records` ADD `script_outcomes` text;',
  },
  {
    idx: 2,
    tag: '0002_next_captain_flint',
    when: 1786079965781,
    hash: '703d5c079d88408a94c9530d169c5a8b9bee2d777d05126555f7ac54388c88af',
    sql: 'ALTER TABLE `workspace_records` ADD `background` text;',
  },
  {
    idx: 3,
    tag: '0003_sudden_sage',
    when: 1786450054262,
    hash: '723c42b449b0ef31ec8bdac0f12eb23b44678776291f400bfb31bbd754282271',
    sql: 'ALTER TABLE `workspace_records` ADD `personal_config` text;--> statement-breakpoint\nALTER TABLE `workspace_records` ADD `legacy_desktop_settings_migrated` integer DEFAULT false NOT NULL;',
  },
];
