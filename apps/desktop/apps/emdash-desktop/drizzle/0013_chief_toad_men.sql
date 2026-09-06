CREATE TABLE `automation_runs` (
	`id` text PRIMARY KEY NOT NULL,
	`automation_id` text NOT NULL,
	`scheduled_at` integer,
	`deadline_at` integer,
	`started_at` integer,
	`finished_at` integer,
	`status` text NOT NULL,
	`task_id` text,
	`created_task_id` text,
	`error` text,
	`trigger_kind` text NOT NULL,
	`worker_id` text,
	FOREIGN KEY (`automation_id`) REFERENCES `automations`(`id`) ON UPDATE no action ON DELETE cascade,
	FOREIGN KEY (`task_id`) REFERENCES `tasks`(`id`) ON UPDATE no action ON DELETE set null
);
--> statement-breakpoint
CREATE TABLE `automations` (
	`id` text PRIMARY KEY NOT NULL,
	`name` text NOT NULL,
	`description` text,
	`category` text NOT NULL,
	`cron_expr` text NOT NULL,
	`cron_tz` text,
	`prompt_template` text DEFAULT '' NOT NULL,
	`actions` text DEFAULT '[]' NOT NULL,
	`task_config` text,
	`project_id` text,
	`enabled` integer DEFAULT 1 NOT NULL,
	`is_draft` integer DEFAULT 0 NOT NULL,
	`last_run_at` integer,
	`next_run_at` integer,
	`deadline_policy` text DEFAULT 'next-interval' NOT NULL,
	`deadline_ms` integer,
	`created_at` integer NOT NULL,
	`updated_at` integer NOT NULL,
	FOREIGN KEY (`project_id`) REFERENCES `projects`(`id`) ON UPDATE no action ON DELETE set null
);
--> statement-breakpoint
CREATE INDEX `idx_automation_runs_automation_started` ON `automation_runs` (`automation_id`,`started_at`);--> statement-breakpoint
CREATE INDEX `idx_automation_runs_automation_scheduled` ON `automation_runs` (`automation_id`,`scheduled_at`);--> statement-breakpoint
CREATE INDEX `idx_automation_runs_automation_status` ON `automation_runs` (`automation_id`,`status`);--> statement-breakpoint
CREATE INDEX `idx_automation_runs_status` ON `automation_runs` (`status`);--> statement-breakpoint
CREATE INDEX `idx_automation_runs_created_task_id` ON `automation_runs` (`created_task_id`);--> statement-breakpoint
CREATE INDEX `idx_automations_enabled_next_run` ON `automations` (`enabled`,`next_run_at`);--> statement-breakpoint
CREATE INDEX `idx_automations_project_id` ON `automations` (`project_id`);