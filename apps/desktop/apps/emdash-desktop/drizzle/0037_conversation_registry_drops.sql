-- Conversation-registry migration train, step 3 of 3: drops and link relaxation.
-- The vestigial messages table drops outright (defined, never written — spec §10.2).
DROP TABLE `messages`;--> statement-breakpoint
-- `conversations.project_id`/`task_id` become nullable (an adopted mirror row has no
-- links) and the legacy `session_id`/`last_interacted_at` columns drop after the 0036
-- data train copied them. SQLite cannot ALTER a NOT NULL constraint, so the table is
-- recreated. The migration runner disables foreign_keys around the transaction, so the
-- DROP TABLE below does not cascade into child tables.
CREATE TABLE `__new_conversations` (
	`id` text PRIMARY KEY NOT NULL,
	`project_id` text,
	`task_id` text,
	`is_initial_conversation` integer,
	`agent_status_seen` integer DEFAULT 1,
	`agent_status` text,
	`title` text NOT NULL,
	`provider` text,
	`type` text,
	`config` text,
	`created_at` text DEFAULT CURRENT_TIMESTAMP NOT NULL,
	`updated_at` text DEFAULT CURRENT_TIMESTAMP NOT NULL,
	`cwd` text,
	`workspace_path` text,
	`provider_session_id` text,
	`id_regime` text,
	`last_session_activity_at` text,
	`observed_status` text,
	`last_observed_at` text,
	`origin` text DEFAULT 'registered' NOT NULL,
	`location` text,
	`ssh_connection_id` text,
	`untracked_at` text,
	FOREIGN KEY (`project_id`) REFERENCES `projects`(`id`) ON UPDATE no action ON DELETE cascade,
	FOREIGN KEY (`task_id`) REFERENCES `tasks`(`id`) ON UPDATE no action ON DELETE cascade,
	FOREIGN KEY (`ssh_connection_id`) REFERENCES `ssh_connections`(`id`) ON UPDATE no action ON DELETE set null
);--> statement-breakpoint
INSERT INTO `__new_conversations` (
	`id`, `project_id`, `task_id`, `is_initial_conversation`, `agent_status_seen`,
	`agent_status`, `title`, `provider`, `type`, `config`, `created_at`, `updated_at`,
	`cwd`, `workspace_path`, `provider_session_id`, `id_regime`,
	`last_session_activity_at`, `observed_status`, `last_observed_at`, `origin`,
	`location`, `ssh_connection_id`, `untracked_at`
)
SELECT
	`id`, `project_id`, `task_id`, `is_initial_conversation`, `agent_status_seen`,
	`agent_status`, `title`, `provider`, `type`, `config`, `created_at`, `updated_at`,
	`cwd`, `workspace_path`, `provider_session_id`, `id_regime`,
	`last_session_activity_at`, `observed_status`, `last_observed_at`, `origin`,
	`location`, `ssh_connection_id`, `untracked_at`
FROM `conversations`;--> statement-breakpoint
DROP TABLE `conversations`;--> statement-breakpoint
ALTER TABLE `__new_conversations` RENAME TO `conversations`;--> statement-breakpoint
CREATE INDEX `idx_conversations_task_id` ON `conversations` (`task_id`);
