ALTER TABLE `automations` ADD `revision` integer DEFAULT 1 NOT NULL;
--> statement-breakpoint
CREATE TABLE `automation_runs_new` (
	`id` text PRIMARY KEY NOT NULL,
	`automation_id` text NOT NULL,
	`automation_name` text NOT NULL,
	`status` text NOT NULL,
	`scheduled_at` integer,
	`started_at` integer,
	`finished_at` integer,
	`seq` integer DEFAULT 0 NOT NULL
);
--> statement-breakpoint
INSERT INTO `automation_runs_new` (
	`id`,
	`automation_id`,
	`automation_name`,
	`status`,
	`scheduled_at`,
	`started_at`,
	`finished_at`,
	`seq`
)
SELECT
	`automation_runs`.`id`,
	`automation_runs`.`automation_id`,
	COALESCE(`automations`.`name`, 'Automation run'),
	`automation_runs`.`status`,
	`automation_runs`.`scheduled_at`,
	`automation_runs`.`started_at`,
	`automation_runs`.`finished_at`,
	0
FROM `automation_runs`
LEFT JOIN `automations` ON `automations`.`id` = `automation_runs`.`automation_id`;
--> statement-breakpoint
DROP TABLE `automation_runs`;
--> statement-breakpoint
ALTER TABLE `automation_runs_new` RENAME TO `automation_runs`;
--> statement-breakpoint
CREATE INDEX `idx_automation_runs_automation_id` ON `automation_runs` (`automation_id`);
--> statement-breakpoint
CREATE UNIQUE INDEX `idx_tasks_active_automation_run_id`
	ON `tasks` (`automation_run_id`)
	WHERE `automation_run_id` IS NOT NULL AND `deleted_at` IS NULL;
