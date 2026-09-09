ALTER TABLE `conversations` ADD `cwd` text;--> statement-breakpoint
ALTER TABLE `conversations` ADD `workspace_path` text;--> statement-breakpoint
ALTER TABLE `conversations` ADD `provider_session_id` text;--> statement-breakpoint
ALTER TABLE `conversations` ADD `id_regime` text;--> statement-breakpoint
ALTER TABLE `conversations` ADD `last_session_activity_at` text;--> statement-breakpoint
ALTER TABLE `conversations` ADD `observed_status` text;--> statement-breakpoint
ALTER TABLE `conversations` ADD `last_observed_at` text;--> statement-breakpoint
ALTER TABLE `conversations` ADD `origin` text DEFAULT 'registered' NOT NULL;--> statement-breakpoint
ALTER TABLE `conversations` ADD `location` text;--> statement-breakpoint
ALTER TABLE `conversations` ADD `ssh_connection_id` text REFERENCES ssh_connections(id);--> statement-breakpoint
ALTER TABLE `conversations` ADD `untracked_at` text;--> statement-breakpoint
/*
 SQLite does not support "Creating foreign key on existing column" out of the box, we do not generate automatic migration for that, so it has to be done manually
 Please refer to: https://www.techonthenet.com/sqlite/tables/alter_table.php
                  https://www.sqlite.org/lang_altertable.html

 Due to that we don't generate migration automatically and it has to be done manually
*/