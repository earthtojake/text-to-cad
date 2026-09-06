/*
 SQLite does not support "Dropping foreign key" out of the box, we do not generate automatic migration for that, so it has to be done manually
 Please refer to: https://www.techonthenet.com/sqlite/tables/alter_table.php
                  https://www.sqlite.org/lang_altertable.html

 Due to that we don't generate migration automatically and it has to be done manually
*/--> statement-breakpoint
DROP INDEX IF EXISTS `idx_automation_runs_created_task_id`;--> statement-breakpoint
DROP INDEX IF EXISTS `idx_automations_enabled_next_run`;--> statement-breakpoint
PRAGMA foreign_keys=OFF;--> statement-breakpoint
CREATE TABLE `__new_automation_runs` (
	`id` text PRIMARY KEY NOT NULL,
	`automation_id` text NOT NULL,
	`scheduled_at` integer,
	`deadline_at` integer,
	`started_at` integer,
	`task_created_at` integer,
	`launched_at` integer,
	`finished_at` integer,
	`status` text NOT NULL,
	`error` text,
	`trigger_kind` text NOT NULL,
	`trigger_config_snapshot` text DEFAULT '{}' NOT NULL,
	`conversation_config_snapshot` text DEFAULT '{}' NOT NULL,
	`task_config_snapshot` text,
	`generated_task_name` text,
	FOREIGN KEY (`automation_id`) REFERENCES `automations`(`id`) ON UPDATE no action ON DELETE cascade
);--> statement-breakpoint
INSERT INTO `__new_automation_runs` (`id`, `automation_id`, `scheduled_at`, `deadline_at`, `started_at`, `finished_at`, `status`, `error`, `trigger_kind`) SELECT `id`, `automation_id`, `scheduled_at`, `deadline_at`, `started_at`, `finished_at`, `status`, `error`, `trigger_kind` FROM `automation_runs`;--> statement-breakpoint
DROP TABLE `automation_runs`;--> statement-breakpoint
ALTER TABLE `__new_automation_runs` RENAME TO `automation_runs`;--> statement-breakpoint
PRAGMA foreign_keys=ON;--> statement-breakpoint
CREATE INDEX `idx_automation_runs_automation_started` ON `automation_runs` (`automation_id`,`started_at`);--> statement-breakpoint
CREATE INDEX `idx_automation_runs_automation_scheduled` ON `automation_runs` (`automation_id`,`scheduled_at`);--> statement-breakpoint
CREATE INDEX `idx_automation_runs_automation_status` ON `automation_runs` (`automation_id`,`status`);--> statement-breakpoint
CREATE INDEX `idx_automation_runs_status` ON `automation_runs` (`status`);--> statement-breakpoint
CREATE INDEX `idx_automation_runs_status_scheduled` ON `automation_runs` (`status`,`scheduled_at`);--> statement-breakpoint
ALTER TABLE `automations` ADD `trigger_config` text;--> statement-breakpoint
ALTER TABLE `automations` ADD `conversation_config` text;--> statement-breakpoint
ALTER TABLE `automations` ADD `deleted_at` integer;--> statement-breakpoint
ALTER TABLE `conversations` ADD `agent_status` text;--> statement-breakpoint
ALTER TABLE `conversations` ADD `agent_status_seen` integer DEFAULT 1;--> statement-breakpoint
ALTER TABLE `tasks` ADD `type` text DEFAULT 'task' NOT NULL;--> statement-breakpoint
ALTER TABLE `tasks` ADD `automation_run_id` text;--> statement-breakpoint
ALTER TABLE `automations` DROP COLUMN `description`;--> statement-breakpoint
ALTER TABLE `automations` DROP COLUMN `category`;--> statement-breakpoint
ALTER TABLE `automations` DROP COLUMN `cron_expr`;--> statement-breakpoint
ALTER TABLE `automations` DROP COLUMN `cron_tz`;--> statement-breakpoint
ALTER TABLE `automations` DROP COLUMN `prompt_template`;--> statement-breakpoint
ALTER TABLE `automations` DROP COLUMN `actions`;--> statement-breakpoint
ALTER TABLE `automations` DROP COLUMN `is_draft`;--> statement-breakpoint
ALTER TABLE `automations` DROP COLUMN `last_run_at`;--> statement-breakpoint
ALTER TABLE `automations` DROP COLUMN `next_run_at`;--> statement-breakpoint
ALTER TABLE `automations` DROP COLUMN `deadline_policy`;--> statement-breakpoint
ALTER TABLE `automations` DROP COLUMN `deadline_ms`;