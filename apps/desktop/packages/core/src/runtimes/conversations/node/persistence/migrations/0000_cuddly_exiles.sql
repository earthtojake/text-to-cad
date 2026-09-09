CREATE TABLE `conversation_records` (
	`id` text PRIMARY KEY NOT NULL,
	`provider` text NOT NULL,
	`type` text NOT NULL,
	`cwd` text NOT NULL,
	`workspace_path` text NOT NULL,
	`created_at` integer NOT NULL,
	`title` text NOT NULL,
	`config` text NOT NULL,
	`provider_link` text NOT NULL,
	`last_session_activity_at` integer,
	`last_spawned_at` integer,
	`last_resume_outcome` text NOT NULL,
	`updated_at` integer NOT NULL
);
