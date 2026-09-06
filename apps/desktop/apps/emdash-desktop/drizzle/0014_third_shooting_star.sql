ALTER TABLE `conversations` ADD `session_id` text;--> statement-breakpoint
ALTER TABLE `projects` ADD `repository_workspace_id` text;--> statement-breakpoint
ALTER TABLE `tasks` ADD `workspace_intent` text;--> statement-breakpoint
ALTER TABLE `workspaces` ADD `kind` text;--> statement-breakpoint
ALTER TABLE `workspaces` ADD `location` text;--> statement-breakpoint
ALTER TABLE `workspaces` ADD `ssh_connection_id` text REFERENCES ssh_connections(id);--> statement-breakpoint
ALTER TABLE `workspaces` ADD `config` text;--> statement-breakpoint
ALTER TABLE `workspaces` ADD `branch_name` text;--> statement-breakpoint
/*
 SQLite does not support "Creating foreign key on existing column" out of the box, we do not generate automatic migration for that, so it has to be done manually
 Please refer to: https://www.techonthenet.com/sqlite/tables/alter_table.php
                  https://www.sqlite.org/lang_altertable.html

 Due to that we don't generate migration automatically and it has to be done manually
*/