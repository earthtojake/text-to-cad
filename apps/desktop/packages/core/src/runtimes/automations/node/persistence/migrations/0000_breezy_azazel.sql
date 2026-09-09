CREATE TABLE `automation_deployments` (
	`automation_id` text PRIMARY KEY NOT NULL,
	`enabled` integer NOT NULL,
	`payload` text NOT NULL,
	`deployed_at` integer NOT NULL
);
--> statement-breakpoint
CREATE TABLE `automation_journal` (
	`singleton` integer PRIMARY KEY NOT NULL,
	`next_seq` integer NOT NULL,
	CONSTRAINT "automation_journal_singleton_check" CHECK("automation_journal"."singleton" = 1)
);
--> statement-breakpoint
CREATE TABLE `automation_runs` (
	`id` text PRIMARY KEY NOT NULL,
	`seq` integer NOT NULL,
	`automation_id` text NOT NULL,
	`status` text NOT NULL,
	`scheduled_at` integer,
	`deadline_at` integer,
	`payload` text NOT NULL
);
--> statement-breakpoint
CREATE UNIQUE INDEX `automation_runs_seq_idx` ON `automation_runs` (`seq`);--> statement-breakpoint
CREATE UNIQUE INDEX `automation_runs_one_scheduled_idx` ON `automation_runs` (`automation_id`) WHERE "automation_runs"."status" = 'scheduled';