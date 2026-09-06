-- Drop old PR bridge/join tables first (they reference pull_requests)
DROP TABLE IF EXISTS `tasks_pull_requests`;
--> statement-breakpoint
DROP TABLE IF EXISTS `project_pull_requests`;
--> statement-breakpoint
-- Drop old pull_request child tables before the parent
DROP TABLE IF EXISTS `pull_request_assignees`;
--> statement-breakpoint
DROP TABLE IF EXISTS `pull_request_labels`;
--> statement-breakpoint
-- Drop old pull_requests table (old schema with id PK / name_with_owner / metadata blob)
DROP TABLE IF EXISTS `pull_requests`;
--> statement-breakpoint

-- pull_request_users: stable GitHub user records
CREATE TABLE `pull_request_users` (
	`user_id` text PRIMARY KEY NOT NULL,
	`user_name` text NOT NULL,
	`display_name` text,
	`avatar_url` text,
	`url` text,
	`user_updated_at` text,
	`user_created_at` text
);
--> statement-breakpoint

-- pull_requests: new schema — url is PK, repositoryUrl for project scoping
CREATE TABLE `pull_requests` (
	`url` text PRIMARY KEY NOT NULL,
	`provider` text DEFAULT 'github' NOT NULL,
	`repository_url` text NOT NULL,
	`base_ref_name` text NOT NULL,
	`base_ref_oid` text NOT NULL,
	`head_repository_url` text NOT NULL,
	`head_ref_name` text NOT NULL,
	`head_ref_oid` text NOT NULL,
	`identifier` text,
	`title` text NOT NULL,
	`description` text,
	`status` text DEFAULT 'open' NOT NULL,
	`is_draft` integer,
	`author_user_id` text REFERENCES `pull_request_users`(`user_id`) ON DELETE set null,
	`additions` integer,
	`deletions` integer,
	`changed_files` integer,
	`commit_count` integer,
	`mergeable_status` text,
	`merge_state_status` text,
	`review_decision` text,
	`pull_request_created_at` text DEFAULT CURRENT_TIMESTAMP NOT NULL,
	`pull_request_updated_at` text DEFAULT CURRENT_TIMESTAMP NOT NULL
);
--> statement-breakpoint
CREATE UNIQUE INDEX `idx_pull_requests_url` ON `pull_requests` (`url`);
--> statement-breakpoint
CREATE INDEX `idx_pull_requests_repository_url` ON `pull_requests` (`repository_url`);
--> statement-breakpoint
CREATE INDEX `idx_pull_requests_head_repository_url` ON `pull_requests` (`head_repository_url`);
--> statement-breakpoint
CREATE INDEX `idx_pull_requests_head_ref_name` ON `pull_requests` (`head_ref_name`);
--> statement-breakpoint

-- pull_request_labels: FK to pull_requests.url
CREATE TABLE `pull_request_labels` (
	`pull_request_id` text NOT NULL,
	`name` text NOT NULL,
	`color` text,
	PRIMARY KEY(`pull_request_id`, `name`),
	FOREIGN KEY (`pull_request_id`) REFERENCES `pull_requests`(`url`) ON UPDATE no action ON DELETE cascade
);
--> statement-breakpoint
CREATE INDEX `idx_prl_name` ON `pull_request_labels` (`name`);
--> statement-breakpoint

-- pull_request_assignees: FK to pull_requests.url + pull_request_users.user_id
CREATE TABLE `pull_request_assignees` (
	`pull_request_url` text NOT NULL,
	`user_id` text NOT NULL,
	PRIMARY KEY(`pull_request_url`, `user_id`),
	FOREIGN KEY (`pull_request_url`) REFERENCES `pull_requests`(`url`) ON UPDATE no action ON DELETE cascade,
	FOREIGN KEY (`user_id`) REFERENCES `pull_request_users`(`user_id`) ON UPDATE no action ON DELETE cascade
);
--> statement-breakpoint
CREATE INDEX `idx_pra_pull_request_url` ON `pull_request_assignees` (`pull_request_url`);
--> statement-breakpoint
CREATE INDEX `idx_pra_user_id` ON `pull_request_assignees` (`user_id`);
--> statement-breakpoint

-- pull_request_checks: stored check runs keyed by commitSha for smart invalidation
CREATE TABLE `pull_request_checks` (
	`id` text PRIMARY KEY NOT NULL,
	`pull_request_url` text NOT NULL,
	`commit_sha` text NOT NULL,
	`name` text NOT NULL,
	`status` text NOT NULL,
	`conclusion` text NOT NULL,
	`details_url` text,
	`started_at` text,
	`completed_at` text,
	`workflow_name` text,
	`app_name` text,
	`app_logo_url` text,
	FOREIGN KEY (`pull_request_url`) REFERENCES `pull_requests`(`url`) ON UPDATE no action ON DELETE cascade
);
--> statement-breakpoint
CREATE INDEX `idx_prc_pull_request_url` ON `pull_request_checks` (`pull_request_url`);
--> statement-breakpoint
CREATE INDEX `idx_prc_commit_sha` ON `pull_request_checks` (`commit_sha`);
--> statement-breakpoint

-- project_remotes: tracks all git remotes per project for PR scoping
CREATE TABLE `project_remotes` (
	`project_id` text NOT NULL,
	`remote_name` text NOT NULL,
	`remote_url` text NOT NULL,
	PRIMARY KEY(`project_id`, `remote_name`),
	FOREIGN KEY (`project_id`) REFERENCES `projects`(`id`) ON UPDATE no action ON DELETE cascade
);
