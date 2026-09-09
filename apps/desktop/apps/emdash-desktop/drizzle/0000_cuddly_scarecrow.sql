CREATE TABLE `app_settings` (
	`key` text PRIMARY KEY NOT NULL,
	`value` text NOT NULL,
	`updated_at` integer DEFAULT CURRENT_TIMESTAMP NOT NULL
);
--> statement-breakpoint
CREATE TABLE `conversations` (
	`id` text PRIMARY KEY NOT NULL,
	`project_id` text NOT NULL,
	`task_id` text NOT NULL,
	`title` text NOT NULL,
	`provider` text,
	`config` text,
	`created_at` text DEFAULT CURRENT_TIMESTAMP NOT NULL,
	`updated_at` text DEFAULT CURRENT_TIMESTAMP NOT NULL,
	FOREIGN KEY (`project_id`) REFERENCES `projects`(`id`) ON UPDATE no action ON DELETE cascade,
	FOREIGN KEY (`task_id`) REFERENCES `tasks`(`id`) ON UPDATE no action ON DELETE cascade
);
--> statement-breakpoint
CREATE TABLE `editor_buffers` (
	`id` text PRIMARY KEY NOT NULL,
	`project_id` text NOT NULL,
	`workspace_id` text NOT NULL,
	`file_path` text NOT NULL,
	`content` text NOT NULL,
	`updated_at` integer NOT NULL,
	FOREIGN KEY (`project_id`) REFERENCES `projects`(`id`) ON UPDATE no action ON DELETE cascade
);
--> statement-breakpoint
CREATE TABLE `kv` (
	`key` text PRIMARY KEY NOT NULL,
	`value` text NOT NULL,
	`updated_at` integer DEFAULT CURRENT_TIMESTAMP NOT NULL
);
--> statement-breakpoint
CREATE TABLE `line_comments` (
	`id` text PRIMARY KEY NOT NULL,
	`task_id` text NOT NULL,
	`file_path` text NOT NULL,
	`line_number` integer NOT NULL,
	`line_content` text,
	`content` text NOT NULL,
	`created_at` text DEFAULT CURRENT_TIMESTAMP NOT NULL,
	`updated_at` text DEFAULT CURRENT_TIMESTAMP NOT NULL,
	`sent_at` text,
	FOREIGN KEY (`task_id`) REFERENCES `tasks`(`id`) ON UPDATE no action ON DELETE cascade
);
--> statement-breakpoint
CREATE TABLE `messages` (
	`id` text PRIMARY KEY NOT NULL,
	`conversation_id` text NOT NULL,
	`content` text NOT NULL,
	`sender` text NOT NULL,
	`timestamp` text DEFAULT CURRENT_TIMESTAMP NOT NULL,
	`metadata` text,
	FOREIGN KEY (`conversation_id`) REFERENCES `conversations`(`id`) ON UPDATE no action ON DELETE cascade
);
--> statement-breakpoint
CREATE TABLE `project_pull_requests` (
	`project_id` text NOT NULL,
	`pull_request_url` text NOT NULL,
	PRIMARY KEY(`project_id`, `pull_request_url`),
	FOREIGN KEY (`project_id`) REFERENCES `projects`(`id`) ON UPDATE no action ON DELETE cascade,
	FOREIGN KEY (`pull_request_url`) REFERENCES `pull_requests`(`url`) ON UPDATE no action ON DELETE cascade
);
--> statement-breakpoint
CREATE TABLE `projects` (
	`id` text PRIMARY KEY NOT NULL,
	`name` text NOT NULL,
	`path` text NOT NULL,
	`workspace_provider` text DEFAULT 'local' NOT NULL,
	`base_ref` text,
	`ssh_connection_id` text,
	`created_at` text DEFAULT CURRENT_TIMESTAMP NOT NULL,
	`updated_at` text DEFAULT CURRENT_TIMESTAMP NOT NULL,
	FOREIGN KEY (`ssh_connection_id`) REFERENCES `ssh_connections`(`id`) ON UPDATE no action ON DELETE set null
);
--> statement-breakpoint
CREATE TABLE `pull_request_assignees` (
	`pull_request_id` text NOT NULL,
	`login` text NOT NULL,
	`avatar_url` text,
	PRIMARY KEY(`pull_request_id`, `login`),
	FOREIGN KEY (`pull_request_id`) REFERENCES `pull_requests`(`id`) ON UPDATE no action ON DELETE cascade
);
--> statement-breakpoint
CREATE TABLE `pull_request_labels` (
	`pull_request_id` text NOT NULL,
	`name` text NOT NULL,
	`color` text,
	PRIMARY KEY(`pull_request_id`, `name`),
	FOREIGN KEY (`pull_request_id`) REFERENCES `pull_requests`(`id`) ON UPDATE no action ON DELETE cascade
);
--> statement-breakpoint
CREATE TABLE `pull_requests` (
	`id` text PRIMARY KEY NOT NULL,
	`provider` text DEFAULT 'github' NOT NULL,
	`name_with_owner` text DEFAULT '' NOT NULL,
	`url` text NOT NULL,
	`title` text NOT NULL,
	`identifier` text,
	`status` text DEFAULT 'open' NOT NULL,
	`author` text,
	`author_login` text,
	`author_display_name` text,
	`author_avatar_url` text,
	`is_draft` integer,
	`head_ref_name` text,
	`metadata` text,
	`created_at` text DEFAULT CURRENT_TIMESTAMP NOT NULL,
	`updated_at` text DEFAULT CURRENT_TIMESTAMP NOT NULL,
	`fetched_at` text DEFAULT CURRENT_TIMESTAMP NOT NULL
);
--> statement-breakpoint
CREATE TABLE `ssh_connections` (
	`id` text PRIMARY KEY NOT NULL,
	`name` text NOT NULL,
	`host` text NOT NULL,
	`port` integer DEFAULT 22 NOT NULL,
	`username` text NOT NULL,
	`auth_type` text DEFAULT 'agent' NOT NULL,
	`private_key_path` text,
	`use_agent` integer DEFAULT 0 NOT NULL,
	`metadata` text,
	`created_at` text DEFAULT CURRENT_TIMESTAMP NOT NULL,
	`updated_at` text DEFAULT CURRENT_TIMESTAMP NOT NULL
);
--> statement-breakpoint
CREATE TABLE `tasks` (
	`id` text PRIMARY KEY NOT NULL,
	`project_id` text NOT NULL,
	`name` text NOT NULL,
	`status` text NOT NULL,
	`source_branch` text NOT NULL,
	`task_branch` text,
	`linked_issue` text,
	`archived_at` text,
	`created_at` text DEFAULT CURRENT_TIMESTAMP NOT NULL,
	`updated_at` text DEFAULT CURRENT_TIMESTAMP NOT NULL,
	`last_interacted_at` text,
	`status_changed_at` text DEFAULT CURRENT_TIMESTAMP NOT NULL,
	`is_pinned` integer DEFAULT 0 NOT NULL,
	FOREIGN KEY (`project_id`) REFERENCES `projects`(`id`) ON UPDATE no action ON DELETE cascade
);
--> statement-breakpoint
CREATE TABLE `tasks_pull_requests` (
	`task_id` text NOT NULL,
	`pull_request_url` text NOT NULL,
	PRIMARY KEY(`task_id`, `pull_request_url`),
	FOREIGN KEY (`task_id`) REFERENCES `tasks`(`id`) ON UPDATE no action ON DELETE cascade,
	FOREIGN KEY (`pull_request_url`) REFERENCES `pull_requests`(`url`) ON UPDATE no action ON DELETE cascade
);
--> statement-breakpoint
CREATE TABLE `terminals` (
	`id` text PRIMARY KEY NOT NULL,
	`project_id` text NOT NULL,
	`task_id` text NOT NULL,
	`ssh` integer DEFAULT 0 NOT NULL,
	`name` text NOT NULL,
	`created_at` text DEFAULT CURRENT_TIMESTAMP NOT NULL,
	`updated_at` text DEFAULT CURRENT_TIMESTAMP NOT NULL,
	FOREIGN KEY (`project_id`) REFERENCES `projects`(`id`) ON UPDATE no action ON DELETE cascade,
	FOREIGN KEY (`task_id`) REFERENCES `tasks`(`id`) ON UPDATE no action ON DELETE cascade
);
--> statement-breakpoint
CREATE UNIQUE INDEX `idx_app_settings_key` ON `app_settings` (`key`);--> statement-breakpoint
CREATE INDEX `idx_conversations_task_id` ON `conversations` (`task_id`);--> statement-breakpoint
CREATE INDEX `idx_editor_buffers_workspace_file` ON `editor_buffers` (`workspace_id`,`file_path`);--> statement-breakpoint
CREATE UNIQUE INDEX `idx_kv_key` ON `kv` (`key`);--> statement-breakpoint
CREATE INDEX `idx_line_comments_task_file` ON `line_comments` (`task_id`,`file_path`);--> statement-breakpoint
CREATE INDEX `idx_messages_conversation_id` ON `messages` (`conversation_id`);--> statement-breakpoint
CREATE INDEX `idx_messages_timestamp` ON `messages` (`timestamp`);--> statement-breakpoint
CREATE INDEX `idx_project_pull_requests_project_id` ON `project_pull_requests` (`project_id`);--> statement-breakpoint
CREATE UNIQUE INDEX `idx_projects_path` ON `projects` (`path`);--> statement-breakpoint
CREATE INDEX `idx_projects_ssh_connection_id` ON `projects` (`ssh_connection_id`);--> statement-breakpoint
CREATE INDEX `idx_pra_login` ON `pull_request_assignees` (`login`);--> statement-breakpoint
CREATE INDEX `idx_prl_name` ON `pull_request_labels` (`name`);--> statement-breakpoint
CREATE UNIQUE INDEX `idx_pull_requests_url` ON `pull_requests` (`url`);--> statement-breakpoint
CREATE INDEX `idx_pull_requests_name_with_owner` ON `pull_requests` (`name_with_owner`);--> statement-breakpoint
CREATE INDEX `idx_pull_requests_author_login` ON `pull_requests` (`author_login`);--> statement-breakpoint
CREATE INDEX `idx_pull_requests_head_ref_name` ON `pull_requests` (`head_ref_name`);--> statement-breakpoint
CREATE UNIQUE INDEX `idx_ssh_connections_name` ON `ssh_connections` (`name`);--> statement-breakpoint
CREATE INDEX `idx_ssh_connections_host` ON `ssh_connections` (`host`);--> statement-breakpoint
CREATE INDEX `idx_tasks_project_id` ON `tasks` (`project_id`);--> statement-breakpoint
CREATE INDEX `idx_terminals_task_id` ON `terminals` (`task_id`);